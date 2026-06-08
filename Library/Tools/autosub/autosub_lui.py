import os
import sys
import subprocess
import time
import warnings

# Suppress annoying FutureWarnings and EOL warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*Python 3.9.*")

# Add common directory to path for llm_utils
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
COMMON_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "common")
sys.path.append(COMMON_DIR)

try:
    from llm_utils import LLMProvider, LLMClient
    HAS_LLM_UTILS = True
except ImportError:
    HAS_LLM_UTILS = False

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def find_potential_cookies():
    """Search for cookies.txt in common Mac locations."""
    home = os.path.expanduser("~")
    potentials = [
        os.path.join(home, "Downloads", "cookies.txt"),
        os.path.join(PROJECT_ROOT, "cookies.txt"),
        os.path.join(CURRENT_DIR, "cookies.txt"),
        os.path.join(CURRENT_DIR, "..", "vdown", "cookies.txt")
    ]
    for p in potentials:
        if os.path.exists(p):
            return os.path.abspath(p)
    return None

def main():
    clear_screen()
    print("========================================")
    print("   AutoSub 自动字幕处理工具 (LUI 模式)   ")
    print("========================================")

    # 1. Input URL or File
    video_input = input("请输入视频 URL 或本地文件路径: ").strip().strip('"').strip("'")
    if not video_input:
        print("❌ 错误：输入不能为空。")
        return

    # 1.5 Cookies Interaction
    manual_p = input("\n请输入 Cookies 文件路径 (回车则自动尝试搜寻 Downloads): ").strip().strip('"').strip("'")
    cookies_path = ""

    if manual_p:
        if os.path.exists(manual_p):
            cookies_path = os.path.abspath(manual_p)
        else:
            print(f"⚠️  警告: 路径 {manual_p} 不存在，将尝试自动搜寻。")
            manual_p = "" # Fallback to search

    if not manual_p:
        found_p = find_potential_cookies()
        if found_p:
            print(f"✨ 自动识别到 Cookies: {found_p}")
            cookies_path = found_p
        else:
            print("ℹ️  未发现可用 Cookies，将尝试直接下载。")

    # 2. Transcription Model (Whisper)
    print("\n--- [第一阶段] 转录模型选择 (Whisper) ---")
    whisper_models = ["large-v2", "medium", "small", "base", "tiny"]
    for i, m in enumerate(whisper_models):
        print(f"[{i+1}] {m}")

    m_choice = input(f"请选择转录模型 [默认 1]: ").strip()
    try:
        model = whisper_models[int(m_choice)-1] if m_choice else "large-v2"
    except:
        model = "large-v2"

    # 3. Translation Vendor & Model (LLM)
    print("\n--- [第二阶段] 翻译厂商选择 (LLM Vendor) ---")
    vendor_map = {
        "1": ("Google Gemini", "gemini"),
        "2": ("Google Vertex AI", "vertex"),
        "3": ("OpenAI", "openai"),
        "4": ("DeepSeek", "deepseek"),
        "5": ("Silicon Flow", "siliconflow"),
        "6": ("Zhipu (GLM)", "zhipu"),
        "7": ("Moonshot (Kimi)", "moonshot"),
        "8": ("Alibaba (Qwen)", "dashscope"),
    }

    for k, v in vendor_map.items():
        print(f"[{k}] {v[0]}")

    v_choice = input("请选择模型厂商 [默认 2]: ").strip()
    if not v_choice: v_choice = "2"

    vendor_display, vendor_id = vendor_map.get(v_choice, vendor_map["2"])

    llm_model = "gemini-1.5-flash" # Default
    if HAS_LLM_UTILS:
        print(f"\n正在从 {vendor_display} 获取可用模型列表...")
        try:
            client = LLMClient()
            provider = LLMProvider(vendor_id)
            models = client.list_models_by_provider(provider)

            if models:
                print(f"--- {vendor_display} 模型列表 ---")
                for i, m in enumerate(models):
                    print(f"[{i+1}] {m}")

                lm_choice = input(f"请选择模型 [默认 1]: ").strip()
                try:
                    llm_model = models[int(lm_choice)-1] if lm_choice else models[0]
                except:
                    llm_model = models[0]
            else:
                print("⚠️  无法获取模型列表，将使用默认值。")
        except Exception as e:
            print(f"⚠️  获取列表失败: {e}")
    else:
        print("⚠️  缺少 llm_utils，使用手动输入。")
        llm_model = input("请输入翻译模型 ID (例如 gemini-3.1-flash-preview): ").strip() or "gemini-3.1-flash-preview"

    # 4. Confirm and Run
    print("\n----------------------------------------")
    print(f"输入源: {video_input}")
    print(f"转录模型: {model}")
    print(f"翻译厂商: {vendor_display}")
    print(f"翻译模型: {llm_model}")
    print("----------------------------------------")

    confirm = input("确认开始处理？(y/n) [默认 y]: ").strip().lower()
    if confirm == 'n':
        print("已取消。")
        return

    # Construct Command
    autosub_script = os.path.join(CURRENT_DIR, "autosub.py")
    cmd = [sys.executable, autosub_script, video_input, "--headless", "--model", model, "--llm-model", llm_model]
    if cookies_path:
        cmd += ["--cookies", cookies_path]

    print("\n🚀 正在启动后台处理流水线...\n")

    try:
        # Run with real-time output
        # Ensure UTF-8 env for Mac
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', env=env)
        for line in process.stdout:
            print(line, end='', flush=True)

        process.wait()
        if process.returncode == 0:
            print("\n✅ 任务处理圆满完成！")
        else:
            print(f"\n❌ 处理失败，退出代码: {process.returncode}")
    except KeyboardInterrupt:
        print("\n⚠️ 任务被用户中止。")
    except Exception as e:
        print(f"\n❌ 发生意外错误: {e}")

if __name__ == "__main__":
    try:
        main()
    except EOFError:
        pass
    except Exception as e:
        print(f"致命错误: {e}")
