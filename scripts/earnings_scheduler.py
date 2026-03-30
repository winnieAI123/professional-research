#!/usr/bin/env python3
"""
Earnings Scheduler — 财报自动追踪与分析调度系统

每日检查 watchlist 中的公司是否发布了新季度财报，
发现新财报且 transcript 可用后自动触发分析 pipeline。

Usage:
    # 日常检查（适合 cron 调用）
    python earnings_scheduler.py

    # 试运行（不实际执行分析，只检查状态）
    python earnings_scheduler.py --dry-run

    # 强制重新分析某个 ticker（忽略 state）
    python earnings_scheduler.py --force BABA

    # 查看当前所有公司状态
    python earnings_scheduler.py --status

Cron 配置示例 (macOS):
    crontab -e
    0 9 * * * cd /Users/winnie/.claude/skills/professional-research && python3 scripts/earnings_scheduler.py >> /tmp/earnings_scheduler.log 2>&1
"""

import os
import sys
import json
import time
import argparse
import logging
import subprocess
from datetime import datetime, timedelta

# ============================================================
# Path setup
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_DIR = os.path.join(SKILL_DIR, 'config')
STATE_FILE = os.path.join(CONFIG_DIR, 'earnings_state.json')
WATCHLIST_FILE = os.path.join(CONFIG_DIR, 'earnings_watchlist.json')

sys.path.insert(0, SCRIPT_DIR)

# Load .env
env_path = os.path.join(SKILL_DIR, '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

# ============================================================
# Logging
# ============================================================
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'

def setup_logging(log_file=None):
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_path = os.path.join(SKILL_DIR, log_file)
        handlers.append(logging.FileHandler(log_path, encoding='utf-8'))
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=handlers)
    return logging.getLogger('earnings_scheduler')


# ============================================================
# State management
# ============================================================
def load_state():
    """Load scheduler state (which quarters have been analyzed)."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_state(state):
    """Persist scheduler state."""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_watchlist():
    """Load the earnings watchlist configuration."""
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# Core: Check for new earnings
# ============================================================
def check_company(ticker, cn_name, state, logger):
    """
    Check if a company has a new quarterly earnings report.

    Returns:
        dict with keys:
            - status: 'new' | 'pending_transcript' | 'already_done' | 'no_data' | 'error'
            - quarter: target quarter string (e.g. "Q4 2025")
            - transcript_available: bool
            - sa_items: SA API items for reuse
            - message: human-readable status message
    """
    from collect_earnings import discover_latest_quarter

    result = {
        'status': 'no_data',
        'quarter': '',
        'transcript_available': False,
        'sa_items': [],
        'message': ''
    }

    try:
        target_q, transcript_avail, sa_items = discover_latest_quarter(ticker, cn_name)

        if not target_q:
            result['message'] = f'{cn_name} ({ticker}): 未检测到任何财报季度'
            return result

        result['quarter'] = target_q
        result['transcript_available'] = transcript_avail
        result['sa_items'] = sa_items

        # Check against state
        last_analyzed = state.get(ticker, {}).get('last_quarter', '')
        if target_q == last_analyzed:
            result['status'] = 'already_done'
            result['message'] = f'{cn_name} ({ticker}): {target_q} 已分析过'
            return result

        # New quarter found!
        if transcript_avail:
            result['status'] = 'new'
            result['message'] = f'{cn_name} ({ticker}): 🆕 {target_q} 财报已出 + Transcript 可用!'
        else:
            result['status'] = 'pending_transcript'
            result['message'] = f'{cn_name} ({ticker}): 🆕 {target_q} 财报已出，但 Transcript 尚未上线'

        return result

    except Exception as e:
        result['status'] = 'error'
        result['message'] = f'{cn_name} ({ticker}): ❌ 检查失败 — {e}'
        return result


# ============================================================
# Core: Run earnings analysis
# ============================================================
def run_analysis(ticker, cn_name, output_dir, logger):
    """
    Run the full earnings analysis pipeline for a single company.

    Calls collect_earnings.py as a subprocess to isolate failures.
    Returns (success: bool, report_path: str or None).
    """
    logger.info(f'🚀 Starting analysis for {cn_name} ({ticker})...')

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, 'collect_earnings.py'),
        '--ticker', ticker,
        '--output', output_dir,
    ]

    logger.info(f'  Command: {" ".join(cmd)}')

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min max per company
            cwd=SKILL_DIR,
        )

        if proc.returncode == 0:
            # Find the generated report
            report_files = [
                f for f in os.listdir(output_dir)
                if f.endswith('_report.md') or f.endswith('_report.docx')
            ]
            report_path = os.path.join(output_dir, report_files[0]) if report_files else None
            logger.info(f'  ✅ Analysis complete! Reports: {report_files}')
            return True, report_path
        else:
            logger.error(f'  ❌ Pipeline failed (exit code {proc.returncode})')
            logger.error(f'  stderr (last 500 chars): {proc.stderr[-500:]}')
            return False, None

    except subprocess.TimeoutExpired:
        logger.error(f'  ❌ Pipeline timed out after 15 minutes')
        return False, None
    except Exception as e:
        logger.error(f'  ❌ Pipeline exception: {e}')
        return False, None


# ============================================================
# Status display
# ============================================================
def show_status(watchlist, state, logger):
    """Display current status of all watched companies."""
    logger.info('=' * 60)
    logger.info('📊 Earnings Scheduler — 当前状态')
    logger.info('=' * 60)

    for company in watchlist['watchlist']:
        ticker = company['ticker']
        cn_name = company['cn_name']
        s = state.get(ticker, {})

        last_q = s.get('last_quarter', '—')
        analyzed_at = s.get('analyzed_at', '—')
        pending = s.get('pending_quarter', '')
        retries = s.get('retry_count', 0)

        status_icon = '✅' if last_q != '—' else '⏳'
        pending_str = f' | 🔄 等待 {pending} transcript (重试 {retries}次)' if pending else ''

        logger.info(f'  {status_icon} {cn_name:6s} ({ticker:6s}) | 已分析: {last_q:8s} | 时间: {analyzed_at}{pending_str}')

    logger.info('=' * 60)


# ============================================================
# Main scheduler loop
# ============================================================
def run_scheduler(dry_run=False, force_ticker=None):
    """
    Main scheduler entry point.

    Args:
        dry_run: If True, only check status without running analysis.
        force_ticker: If set, force re-analysis for this ticker regardless of state.
    """
    watchlist = load_watchlist()
    state = load_state()
    settings = watchlist.get('settings', {})

    logger = setup_logging(settings.get('log_file'))

    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d %H:%M')
    output_base = settings.get('output_base_dir', '/Users/winnie/clauderesult')

    logger.info('=' * 60)
    logger.info(f'📅 Earnings Scheduler — {date_str}')
    logger.info(f'   Watchlist: {len(watchlist["watchlist"])} companies')
    logger.info(f'   Mode: {"🔍 DRY RUN" if dry_run else "🚀 LIVE"}')
    if force_ticker:
        logger.info(f'   Force: {force_ticker}')
    logger.info('=' * 60)

    companies_to_check = watchlist['watchlist']
    if force_ticker:
        companies_to_check = [c for c in companies_to_check if c['ticker'] == force_ticker]
        if not companies_to_check:
            logger.error(f'Ticker {force_ticker} not found in watchlist!')
            return

    results_summary = []
    analysis_queue = []

    # Phase 1: Check all companies
    logger.info('\n📡 Phase 1: 检查各公司财报状态...\n')

    for company in companies_to_check:
        ticker = company['ticker']
        cn_name = company['cn_name']

        result = check_company(ticker, cn_name, state, logger)
        logger.info(f'  {result["message"]}')
        results_summary.append(result)

        if force_ticker and ticker == force_ticker:
            # Force mode: always queue for analysis
            if result['quarter']:
                analysis_queue.append((company, result))
                logger.info(f'  → 强制模式，加入分析队列')
        elif result['status'] == 'new':
            analysis_queue.append((company, result))
        elif result['status'] == 'pending_transcript':
            # Update retry state
            retry_count = state.get(ticker, {}).get('retry_count', 0)
            max_retries = settings.get('retry_max_days', 5)

            if retry_count >= max_retries:
                # Exceeded retry limit — run without transcript
                logger.info(f'  → ⚠ 已重试 {retry_count} 次，将不等待 transcript 直接分析')
                analysis_queue.append((company, result))
            else:
                state[ticker] = {
                    **state.get(ticker, {}),
                    'pending_quarter': result['quarter'],
                    'retry_count': retry_count + 1,
                    'last_check': now.isoformat(),
                }

        # Rate limit: small delay between SA API calls
        time.sleep(1)

    # Phase 2: Run analysis for new earnings
    if analysis_queue:
        logger.info(f'\n🔬 Phase 2: 分析 {len(analysis_queue)} 家公司的新财报...\n')

        for company, result in analysis_queue:
            ticker = company['ticker']
            cn_name = company['cn_name']
            quarter = result['quarter']

            # Create output directory
            date_folder = now.strftime('claude%m%d')
            output_dir = os.path.join(output_base, date_folder, f'earnings_{ticker.lower()}')

            if dry_run:
                logger.info(f'  [DRY RUN] 将分析: {cn_name} ({ticker}) {quarter}')
                logger.info(f'  [DRY RUN] 输出目录: {output_dir}')
                continue

            success, report_path = run_analysis(ticker, cn_name, output_dir, logger)

            if success:
                # Update state
                state[ticker] = {
                    'last_quarter': quarter,
                    'analyzed_at': now.isoformat(),
                    'report_path': report_path,
                    'retry_count': 0,
                    'pending_quarter': '',
                }
                logger.info(f'  ✅ {cn_name} {quarter} 分析完成 → {report_path}')
            else:
                logger.error(f'  ❌ {cn_name} {quarter} 分析失败')
                state[ticker] = {
                    **state.get(ticker, {}),
                    'last_error': now.isoformat(),
                    'error_quarter': quarter,
                }

            # Cooldown between companies to respect API limits
            if len(analysis_queue) > 1:
                logger.info(f'  ⏳ 等待 60 秒再处理下一家...')
                time.sleep(60)
    else:
        logger.info('\n✅ Phase 2: 无新财报需要分析\n')

    # Save state
    save_state(state)

    # Summary
    new_count = sum(1 for r in results_summary if r['status'] == 'new')
    pending_count = sum(1 for r in results_summary if r['status'] == 'pending_transcript')
    done_count = sum(1 for r in results_summary if r['status'] == 'already_done')
    error_count = sum(1 for r in results_summary if r['status'] == 'error')

    logger.info('=' * 60)
    logger.info(f'📋 Summary: 新发现 {new_count} | 等待transcript {pending_count} | 已完成 {done_count} | 错误 {error_count}')
    logger.info('=' * 60)


# ============================================================
# CLI
# ============================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Earnings Scheduler — 财报自动追踪与分析调度',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python earnings_scheduler.py              # 日常检查 + 自动分析
  python earnings_scheduler.py --dry-run    # 只检查不分析
  python earnings_scheduler.py --force BABA # 强制重新分析阿里
  python earnings_scheduler.py --status     # 查看所有公司状态
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='只检查状态，不执行分析')
    parser.add_argument('--force', metavar='TICKER',
                        help='强制重新分析指定 ticker（忽略已分析状态）')
    parser.add_argument('--status', action='store_true',
                        help='显示所有公司当前分析状态')

    args = parser.parse_args()

    if args.status:
        wl = load_watchlist()
        st = load_state()
        lg = setup_logging()
        show_status(wl, st, lg)
    else:
        run_scheduler(dry_run=args.dry_run, force_ticker=args.force)
