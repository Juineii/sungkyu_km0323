import requests
import time
import os
import subprocess
import pandas as pd
from datetime import datetime

# ================== 配置 ==================
CSV_FILENAME = "崔立于台北线下签售.csv"          # CSV 文件名
GITHUB_REPO = "Juineii/chueiliyu_km0323"       # 请替换为您的仓库名
GITHUB_BRANCH = "main"                         # 分支名（main 或 master）
# GitHub Personal Access Token 优先从环境变量 GITHUB_TOKEN 读取，否则需硬编码（不安全，仅测试用）

URL_TAIWAN = "https://www.kmonstar.com.tw/products/%E6%87%89%E5%8B%9F-260403-chuei-li-yu-1st-photo-book-white-letters-%E5%B0%88%E8%BC%AF%E7%99%BC%E8%A1%8C%E7%B4%80%E5%BF%B5%E7%B0%BD%E5%90%8D%E6%9C%83-in-taipei.json"
URL_INTERNATIONAL = "https://kmonstar.com/api/v1/event/detail/932abdf1-6717-40e6-a46d-5a49af3031a5"

HEADERS_INTERNATIONAL = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://kmonstar.org/zh/eventproductdetail/873a6d5e-92af-42e4-8bf4-68eb824d9cdb",
    "Origin": "https://kmonstar.org",
    "Cookie": "nation=KR"
}

# ================== Git 推送函数 ==================
def git_push_update():
    """
    将最新的 CSV 文件提交并推送到 GitHub
    """
    try:
        # 获取 GitHub Token（优先从环境变量读取）
        token = os.environ.get('GITHUB_TOKEN')
        if not token:
            # 如果环境变量未设置，提示用户（这里不硬编码，防止泄露）
            print("⚠️ 环境变量 GITHUB_TOKEN 未设置，跳过 Git 推送")
            return

        # 构建带认证的远程仓库 URL
        remote_url = f"https://{token}@github.com/{GITHUB_REPO}.git"

        # 添加 CSV 文件到暂存区
        subprocess.run(['git', 'add', CSV_FILENAME], check=True, capture_output=True)

        # 检查是否有文件变化（避免空提交）
        result = subprocess.run(['git', 'diff', '--cached', '--quiet'], capture_output=True)
        if result.returncode != 0:
            # 有变化，提交
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_msg = f"自动更新数据 {timestamp}"
            subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)

            # 推送到 GitHub（指定分支）
            subprocess.run(
                ['git', 'push', remote_url, f'HEAD:{GITHUB_BRANCH}'],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"✅ 已推送到 GitHub: {commit_msg}")
        else:
            print("⏭️ CSV 文件无变化，跳过推送")

    except subprocess.CalledProcessError as e:
        print(f"❌ Git 操作失败: {e.stderr if e.stderr else e}")
    except Exception as e:
        print(f"❌ 推送过程中发生错误: {e}")

# ================== pandas 存储函数 ==================
def save_to_csv(data_rows):
    """
    使用 pandas 将新数据行追加到 CSV 文件，并触发 Git 推送
    data_rows: list of lists, 每行格式 [时间, 商品名称, 库存变化, 单笔销量]
    """
    try:
        # 1. 如果文件存在，读取现有数据；否则创建空 DataFrame
        if os.path.exists(CSV_FILENAME):
            df_existing = pd.read_csv(CSV_FILENAME, encoding='utf-8-sig')
        else:
            df_existing = pd.DataFrame(columns=['时间', '商品名称', '库存变化', '单笔销量'])

        # 2. 将新数据行转换为 DataFrame 并拼接
        new_rows_df = pd.DataFrame(data_rows, columns=['时间', '商品名称', '库存变化', '单笔销量'])
        df_updated = pd.concat([df_existing, new_rows_df], ignore_index=True)

        # 3. 保存回 CSV（覆盖原文件）
        df_updated.to_csv(CSV_FILENAME, index=False, encoding='utf-8-sig')

        # 4. 打印存储的内容（与原格式一致）
        for row in data_rows:
            print(f"{row[0]} - 商品名称: {row[1]}, 库存变化: {row[2]}, 单笔销量: {row[3]}")

        # 5. 触发 Git 推送
        git_push_update()

        return True
    except Exception as e:
        print(f"❌ 写入CSV文件失败: {e}")
        return False

# ================== 库存获取函数（保持不变） ==================
def get_stock_taiwan():
    """获取台湾地址商品库存"""
    try:
        resp = requests.get(URL_TAIWAN)
        resp.raise_for_status()
        data = resp.json()
        return data['variants'][0]['inventory_quantity']
    except Exception:
        return None

def get_stock_international():
    """获取国际地址商品库存"""
    try:
        resp = requests.get(URL_INTERNATIONAL, headers=HEADERS_INTERNATIONAL)
        resp.raise_for_status()
        data = resp.json()
        return data['data']['optionList'][0]['stockKo']['quantity']
    except Exception:
        return None

# ================== 主监控函数（保持不变） ==================
def monitor():
    taiwan_last = 0
    taiwan_previous = None
    taiwan_first_logged = False

    international_previous = None
    international_first_logged = False

    while True:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data_rows = []

        # ---------- 处理台湾地址 ----------
        stock_tw = get_stock_taiwan()
        if stock_tw is not None:
            # 初始化第一行数据
            if taiwan_previous is None and not taiwan_first_logged:
                taiwan_previous = stock_tw
                data_rows.append([
                    current_time,
                    '台湾地址',
                    f"初始销量: {stock_tw}",
                    abs(stock_tw)          # 初始销量取绝对值
                ])
                taiwan_first_logged = True

            if stock_tw != taiwan_last and taiwan_last != 0:
                change = taiwan_last - stock_tw
                data_rows.append([
                    current_time,
                    '台湾地址',
                    f"{taiwan_last} -> {stock_tw}",
                    change
                ])
                taiwan_last = stock_tw
            elif taiwan_last == 0 and stock_tw != taiwan_previous:
                taiwan_last = stock_tw

        # ---------- 处理国际地址 ----------
        stock_int = get_stock_international()
        if stock_int is not None:
            # 初始化第一行数据
            if international_previous is None and not international_first_logged:
                international_previous = stock_int
                data_rows.append([
                    current_time,
                    '国际地址',
                    f"初始库存: {stock_int}",
                    0         # 初始销量取绝对值
                ])
                international_first_logged = True
            elif stock_int != international_previous:
                diff = international_previous - stock_int
                data_rows.append([
                    current_time,
                    '国际地址',
                    f"{international_previous} -> {stock_int}",
                    diff
                ])
                international_previous = stock_int

        # 如果有新数据，写入 CSV
        if data_rows:
            save_to_csv(data_rows)

        time.sleep(10)

if __name__ == "__main__":
    monitor()