#!/usr/bin/env python3
"""
Earnings Scheduler — 财报自动追踪与分析调度系统

核心逻辑：
  每次运行时，对 watchlist 中的每家公司：
  1. 通过 SA API 检查最新财报季度及其发布日期
  2. 如果财报发布在 N 天内（freshness_window）→ 尝试获取数据并分析
  3. 如果超过 N 天 → 跳过（已过时效窗口）
  4. 如果已分析过该季度 → 跳过（不重复分析）
  5. 如果 transcript 尚未上线 → 标记等待，下次运行再检查

Usage:
    # 日常检查（适合 cron / 手动）
    python earnings_scheduler.py

    # 试运行（不实际执行分析，只检查状态）
    python earnings_scheduler.py --dry-run

    # 强制重新分析某个 ticker（忽略 state 和窗口期）
    python earnings_scheduler.py --force BABA

    # 查看当前所有公司状态
    python earnings_scheduler.py --status
"""

import os
import sys
import re
import json
import time
import argparse
import logging
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
# Email Notification
# ============================================================
def send_email_notification(cn_name, ticker, quarter, report_path, logger):
    """Send an email notification when a new earnings report is ready."""
    sender = os.environ.get('EMAIL_SENDER', 'wangtian_winnie@163.com')
    password = os.environ.get('EMAIL_PASSWORD', '')
    # 默认发给自己（可用逗号分隔多个邮箱）
    receiver = os.environ.get('EMAIL_RECEIVERS', 'wangtian_winnie@163.com,2386089104@qq.com')
    
    if not password:
        logger.warning("  [Email] 缺少 EMAIL_PASSWORD 环境变量，跳过发送邮件。")
        return
        
    subject = f"🔔 [新财报到达] {cn_name} ({ticker}) {quarter} 深度分析已出炉"
    body = (
        f"Hi Winnie,\n\n"
        f"全自动财报监控系统就在刚刚捕获并完成了：【{cn_name} ({ticker}) {quarter}】的最新的分析！\n\n"
        f"报告全文（含图表和长文总结）已经默默保存在了你的电脑里，完整路径如下：\n"
        f"{report_path}\n\n"
        f"下次有空打开电脑时直接去看吧~\n\n"
        f"-- \nAI Earnings Scheduler (由 Launchd 后台忠实执行)"
    )
    
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = receiver
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    try:
        # 使用你跑通的 163 邮箱配置
        server = smtplib.SMTP('smtp.163.com', 25)
        server.login(sender, password)
        # 支持发给多个接收人
        to_addrs = [r.strip() for r in receiver.split(',')]
        server.send_message(msg, to_addrs=to_addrs)
        server.quit()
        logger.info(f"  📧 邮件通知已发送至 {receiver}")
    except Exception as e:
        logger.error(f"  📧 邮件发送异常: {e}")


# ============================================================
# Helper: Extract earnings publish date from SA API items
# ============================================================
def _get_earnings_publish_date(sa_items, target_quarter):
    """
    Find the earliest publish date among SA items matching the target quarter.

    SA items include both "presentation" and "transcript" entries.
    The presentation is usually published on earnings day,
    so the earliest publishOn date ≈ actual earnings announcement date.

    Args:
        sa_items: Raw SA API data list
        target_quarter: e.g. "Q4 2025"

    Returns:
        datetime object of earliest publish, or None if not found.
    """
    dates = []
    for item in sa_items:
        attrs = item.get('attributes', {})
        title = attrs.get('title', '')
        pub_date_str = attrs.get('publishOn', '')[:10]  # "2026-03-25"

        # Match quarter in title
        qm = re.search(r'Q(\d)\s+(\d{4})', title)
        if qm and f"Q{qm.group(1)} {qm.group(2)}" == target_quarter:
            try:
                dates.append(datetime.strptime(pub_date_str, '%Y-%m-%d'))
            except (ValueError, TypeError):
                pass

    return min(dates) if dates else None


# ============================================================
# Core: Check for new earnings
# ============================================================
def check_company(ticker, cn_name, state, freshness_window, logger):
    """
    Check if a company has a new quarterly earnings report within the freshness window.

    Decision flow:
        1. Discover latest quarter via SA API
        2. Already analyzed? → skip
        3. Published > N days ago? → stale, skip
        4. Transcript available? → ready to analyze
        5. Transcript not available? → waiting (will check again next run)

    Returns:
        dict with keys:
            - status: 'ready' | 'waiting_transcript' | 'already_done' | 'stale' | 'no_data' | 'error'
            - quarter: target quarter string (e.g. "Q4 2025")
            - publish_date: datetime or None
            - days_since_publish: int or None
            - transcript_available: bool
            - sa_items: SA API items for reuse
            - message: human-readable status message
    """
    from collect_earnings import discover_latest_quarter

    result = {
        'status': 'no_data',
        'quarter': '',
        'publish_date': None,
        'days_since_publish': None,
        'transcript_available': False,
        'sa_items': [],
        'message': '',
    }

    try:
        target_q, transcript_avail, sa_items = discover_latest_quarter(ticker, cn_name)

        if not target_q:
            result['message'] = f'{cn_name} ({ticker}): 未检测到任何财报季度'
            return result

        result['quarter'] = target_q
        result['transcript_available'] = transcript_avail
        result['sa_items'] = sa_items

        # ---- Step 1: Already analyzed this quarter? ----
        last_analyzed = state.get(ticker, {}).get('last_quarter', '')
        if target_q == last_analyzed:
            result['status'] = 'already_done'
            analyzed_at = state.get(ticker, {}).get('analyzed_at', '?')[:10]
            result['message'] = f'{cn_name} ({ticker}): {target_q} 已于 {analyzed_at} 分析过'
            return result

        # ---- Step 2: Check freshness window ----
        publish_date = _get_earnings_publish_date(sa_items, target_q)
        result['publish_date'] = publish_date

        if publish_date:
            days_ago = (datetime.now() - publish_date).days
            result['days_since_publish'] = days_ago

            if days_ago > freshness_window:
                result['status'] = 'stale'
                result['message'] = (
                    f'{cn_name} ({ticker}): {target_q} 发布于 {publish_date.strftime("%m-%d")} '
                    f'({days_ago} 天前)，超出 {freshness_window} 天窗口期 → 跳过'
                )
                return result

        # ---- Step 3: Within window — check transcript availability ----
        days_str = f'{result["days_since_publish"]}天前' if result['days_since_publish'] is not None else '日期未知'

        if transcript_avail:
            result['status'] = 'ready'
            result['message'] = (
                f'{cn_name} ({ticker}): 🆕 {target_q} ({days_str}) '
                f'→ PR + Transcript 均已就绪!'
            )
        else:
            result['status'] = 'waiting_transcript'
            result['message'] = (
                f'{cn_name} ({ticker}): ⏳ {target_q} ({days_str}) '
                f'→ 财报已出但 Transcript 尚未上线，下次再查'
            )

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
    logger.info(f'  🚀 开始分析 {cn_name} ({ticker})...')

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, 'collect_earnings.py'),
        '--ticker', ticker,
        '--output', output_dir,
    ]

    logger.info(f'     命令: {" ".join(cmd)}')

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min max per company
            cwd=SKILL_DIR,
        )

        if proc.returncode == 0:
            report_files = [
                f for f in os.listdir(output_dir)
                if f.endswith('_report.md') or f.endswith('_report.docx')
            ]
            report_path = os.path.join(output_dir, report_files[0]) if report_files else None
            logger.info(f'     ✅ 分析完成! 报告: {report_files}')
            return True, report_path
        else:
            logger.error(f'     ❌ Pipeline 失败 (exit code {proc.returncode})')
            # Show last few lines of stderr for debugging
            stderr_lines = proc.stderr.strip().split('\n')
            for line in stderr_lines[-5:]:
                logger.error(f'        {line}')
            return False, None

    except subprocess.TimeoutExpired:
        logger.error(f'     ❌ Pipeline 超时 (15 分钟)')
        return False, None
    except Exception as e:
        logger.error(f'     ❌ 异常: {e}')
        return False, None


# ============================================================
# Status display
# ============================================================
def show_status(watchlist, state, logger):
    """Display current status of all watched companies."""
    logger.info('=' * 65)
    logger.info('📊 Earnings Scheduler — 当前状态')
    logger.info('=' * 65)

    for company in watchlist['watchlist']:
        ticker = company['ticker']
        cn_name = company['cn_name']
        s = state.get(ticker, {})

        last_q = s.get('last_quarter', '—')
        analyzed_at = s.get('analyzed_at', '')[:10] if s.get('analyzed_at') else '—'

        status_icon = '✅' if last_q != '—' else '⬜'

        logger.info(
            f'  {status_icon} {cn_name:6s} ({ticker:6s}) '
            f'| 最近分析: {last_q:8s} ({analyzed_at})'
        )

    freshness = watchlist.get('settings', {}).get('freshness_window_days', 5)
    logger.info(f'\n  ⚙️  窗口期: {freshness} 天 | State: {STATE_FILE}')
    logger.info('=' * 65)


# ============================================================
# Main scheduler
# ============================================================
def run_scheduler(dry_run=False, force_ticker=None):
    """
    Main scheduler entry point.

    Args:
        dry_run: If True, only check status without running analysis.
        force_ticker: If set, force re-analysis for this ticker (ignores state AND window).
    """
    watchlist = load_watchlist()
    state = load_state()
    settings = watchlist.get('settings', {})
    freshness_window = settings.get('freshness_window_days', 5)

    logger = setup_logging(settings.get('log_file'))

    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d %H:%M')
    output_base = settings.get('output_base_dir', '/Users/winnie/clauderesult')

    logger.info('=' * 65)
    logger.info(f'📅 Earnings Scheduler — {date_str}')
    logger.info(f'   Watchlist: {len(watchlist["watchlist"])} 家公司')
    logger.info(f'   窗口期: {freshness_window} 天')
    logger.info(f'   模式: {"🔍 试运行 (DRY RUN)" if dry_run else "🚀 正式运行"}')
    if force_ticker:
        logger.info(f'   强制分析: {force_ticker}')
    logger.info('=' * 65)

    # Filter companies if force mode
    companies_to_check = watchlist['watchlist']
    if force_ticker:
        companies_to_check = [c for c in companies_to_check if c['ticker'] == force_ticker]
        if not companies_to_check:
            logger.error(f'❌ Ticker {force_ticker} 不在 watchlist 中!')
            return

    # ---- Phase 1: Check all companies ----
    logger.info(f'\n📡 Phase 1: 检查各公司财报状态...\n')

    results = []
    analysis_queue = []

    for company in companies_to_check:
        ticker = company['ticker']
        cn_name = company['cn_name']

        # For --force mode, skip state/window checks entirely
        if force_ticker and ticker == force_ticker:
            from collect_earnings import discover_latest_quarter
            target_q, transcript_avail, sa_items = discover_latest_quarter(ticker, cn_name)
            if target_q:
                result = {
                    'status': 'ready',
                    'quarter': target_q,
                    'transcript_available': transcript_avail,
                    'message': f'{cn_name} ({ticker}): 🔧 强制模式 → {target_q}',
                }
                logger.info(f'  {result["message"]}')
                results.append(result)
                analysis_queue.append((company, result))
            else:
                logger.warning(f'  {cn_name} ({ticker}): 强制模式但未找到任何季度数据')
        else:
            result = check_company(ticker, cn_name, state, freshness_window, logger)
            logger.info(f'  {result["message"]}')
            results.append(result)

            if result['status'] == 'ready':
                analysis_queue.append((company, result))

        # Rate limit between SA API calls
        time.sleep(1)

    # ---- Phase 2: Run analysis ----
    if analysis_queue:
        logger.info(f'\n🔬 Phase 2: 分析 {len(analysis_queue)} 家公司的新财报...\n')

        for i, (company, result) in enumerate(analysis_queue):
            ticker = company['ticker']
            cn_name = company['cn_name']
            quarter = result['quarter']

            # Build output directory
            date_folder = now.strftime('claude%m%d')
            output_dir = os.path.join(output_base, date_folder, f'earnings_{ticker.lower()}')

            if dry_run:
                logger.info(f'  [DRY RUN] 将分析: {cn_name} ({ticker}) {quarter}')
                logger.info(f'            输出目录: {output_dir}')
                continue

            success, report_path = run_analysis(ticker, cn_name, output_dir, logger)

            if success:
                state[ticker] = {
                    'last_quarter': quarter,
                    'analyzed_at': now.isoformat(),
                    'report_path': report_path,
                }
                logger.info(f'  ✅ {cn_name} {quarter} → {report_path}')
                
                # 📢 调用邮件提醒发送器
                send_email_notification(cn_name, ticker, quarter, report_path, logger)
            else:
                logger.error(f'  ❌ {cn_name} {quarter} 分析失败')

            # Cooldown between companies (skip after last one)
            if i < len(analysis_queue) - 1:
                logger.info(f'  ⏳ 等待 60 秒再处理下一家...')
                time.sleep(60)
    else:
        logger.info(f'\n💤 Phase 2: 无需分析\n')

    # ---- Save state ----
    save_state(state)

    # ---- Summary ----
    ready_count = sum(1 for r in results if r['status'] == 'ready')
    waiting_count = sum(1 for r in results if r['status'] == 'waiting_transcript')
    stale_count = sum(1 for r in results if r['status'] == 'stale')
    done_count = sum(1 for r in results if r['status'] == 'already_done')
    error_count = sum(1 for r in results if r['status'] == 'error')

    logger.info('=' * 65)
    logger.info(
        f'📋 汇总: '
        f'✅ 可分析 {ready_count} | '
        f'⏳ 等transcript {waiting_count} | '
        f'⏭ 已过期 {stale_count} | '
        f'✔ 已完成 {done_count} | '
        f'❌ 错误 {error_count}'
    )
    logger.info('=' * 65)


# ============================================================
# CLI
# ============================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Earnings Scheduler — 财报自动追踪与分析调度',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python earnings_scheduler.py              # 日常检查 + 自动分析
  python earnings_scheduler.py --dry-run    # 只检查不分析
  python earnings_scheduler.py --force BABA # 强制重新分析阿里
  python earnings_scheduler.py --status     # 查看所有公司状态
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='只检查状态，不执行分析')
    parser.add_argument('--force', metavar='TICKER',
                        help='强制重新分析指定 ticker（忽略已分析状态和窗口期）')
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
