# Hướng dẫn cài đặt trên MacBook M2 8 GB

Hướng dẫn từng bước, từ máy trống đến khi khách dùng được chatbot. Mô hình triển khai: **máy Mac là server duy nhất** (API, giao diện, cơ sở dữ liệu, file tài liệu). Chat dùng OpenAI qua internet. Không cần GPU rời, không cần Docker.

> **Chưa kiểm thử trên Mac.** Dự án được phát triển và chạy thử trên Linux (GPU NVIDIA). Các bước dưới đây đã điều chỉnh cho Apple Silicon (`RAG_DEVICE=mps`) nhưng chưa chạy thật trên M2. Nên cài thử trước một lần tại chỗ của bạn, rồi mới mang đến khách. Các chỗ chưa chắc được đánh dấu **[chưa kiểm chứng]**.

## 0. Tổng quan và yêu cầu

| Thành phần | Chạy ở đâu | Ghi chú |
| --- | --- | --- |
| API + giao diện web | Mac (cổng 8080) | FastAPI, một tiến trình |
| Embedding `bge-m3` + reranker `bge-reranker-v2-m3` | Mac (GPU Apple, `mps`) | tải ≈ 4,5 GB lần đầu, dùng ≈ 2,5 GB RAM |
| Chat | OpenAI API | cần khóa API và internet |
| OCR cho PDF scan | Gemini API **hoặc** MinerU local | xem mục 6 |
| Dữ liệu | thư mục `data/` trên Mac | SQLite, PDF gốc, cache OCR |

Cần có:

- macOS 13 trở lên, ổ trống ≥ 15 GB, internet ổn định.
- Khóa OpenAI (`sk-...`). Khóa Gemini nếu dùng OCR Gemini.
- Tài khoản GitHub có quyền đọc repo `hiimmuc/banking-chatbot-rag` (nhánh `dev`).
- Bộ PDF tài liệu của khách.

**Ngân sách RAM 8 GB:** macOS + trình duyệt đã dùng ≈ 4 GB, embedding + reranker ≈ 2,5 GB. Chỉ còn rất ít chỗ. Quy tắc: **đóng ứng dụng nặng, không chạy OCR MinerU cùng lúc với API**.

## 1. Cài công cụ nền

Mở **Terminal** (Cmd + Space, gõ `Terminal`).

**1.1. Công cụ dòng lệnh của Apple**

```bash
xcode-select --install
```

**1.2. Homebrew** (trình quản lý gói)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Cuối quá trình Homebrew in hai dòng bắt đầu bằng `echo` và `eval` để thêm vào PATH. Chạy đúng hai dòng đó, rồi kiểm tra:

```bash
brew --version
```

**1.3. Git, uv (quản lý Python)**

```bash
brew install git uv
```

**1.4. Kiểm tra**

```bash
git --version && uv --version
```

## 2. Lấy mã nguồn

```bash
mkdir -p ~/apps && cd ~/apps
git clone -b dev git@github.com:hiimmuc/banking-chatbot-rag.git banking-rag
cd banking-rag
```

Nếu báo lỗi quyền (`Permission denied (publickey)`), chưa có khóa SSH GitHub trên máy này. Dùng HTTPS thay thế (GitHub sẽ hỏi tài khoản và token):

```bash
git clone -b dev https://github.com/hiimmuc/banking-chatbot-rag.git banking-rag
```

## 3. Cài môi trường Python

```bash
uv venv --python 3.10 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

Bước này tải PyTorch và các thư viện, mất vài phút. **[chưa kiểm chứng]** Nếu `torch==2.11.0` không có bản cho macOS, đổi dòng đó trong `requirements.txt` thành `torch` rồi chạy lại.

Kiểm tra GPU Apple dùng được:

```bash
.venv/bin/python -c "import torch; print(torch.backends.mps.is_available())"
```

Phải in `True`. Nếu in `False`, dùng `RAG_DEVICE=cpu` ở bước 4 (chạy được nhưng chậm hơn nhiều).

## 4. Cấu hình `.env`

```bash
cp .env.example .env
chmod 600 .env
open -e .env
```

`.env.example` che các giá trị nhạy cảm bằng `***REMOVED***`; bạn điền giá trị thật vào `.env`. Các dòng cần sửa:

```ini
# --- chat ---
CHAT_PROVIDER=openai
OPENAI_API_KEY=sk-...                 # khóa của khách
OPENAI_CHAT_MODEL=gpt-4.1-mini,gpt-5.4-mini   # mục đầu là mặc định
QWEN_BASE_URL=                        # để trống: ẩn lựa chọn Qwen local
GEMINI_API_KEY=                       # chỉ điền nếu dùng OCR Gemini

# --- OCR ---
OCR_BACKEND=gemini                    # khuyến nghị cho Mac 8 GB (xem mục 6)

# --- thiết bị tính toán ---
RAG_DEVICE=mps                        # cpu nếu mps không dùng được

# --- thương hiệu (tùy chọn, để trống thì hiện chỗ đặt logo) ---
ORG_NAME=Tên đơn vị
AUTHOR_INFO=Họ tên - Đơn vị
BRAND_LOGO_HEADER=
BRAND_LOGO_FOOTER_LIGHT=
BRAND_LOGO_FOOTER_DARK=

# --- truy cập ---
APP_USER=admin
APP_PASSWORD=                         # BẮT BUỘC đặt nếu mở ra internet (mục 9)
ALLOW_CUSTOM_ENDPOINTS=0
```

Ghi chú:

- Logo: đặt file `png/webp/jpg` vào thư mục `private/brand/` rồi ghi đường dẫn, ví dụ `BRAND_LOGO_HEADER=private/brand/logo.png`. Không dùng SVG.
- Giá trị trống, `***REMOVED***` hoặc bắt đầu bằng `your-` được coi là chưa đặt.
- **Không gửi `.env` qua chat hay email.** File này đã nằm trong `.gitignore`.

## 5. Nạp tài liệu

**5.1. Đưa PDF vào**

```bash
mkdir -p data/raw
cp /đường/dẫn/tới/*.pdf data/raw/
```

Tên file nên bắt đầu bằng mã văn bản (ví dụ `66CNTI_...pdf`), vì mã này dùng làm ID tài liệu.

**5.2. Tải trước model embedding** (tránh chờ ở lần chạy đầu, ≈ 4,5 GB):

```bash
.venv/bin/python -c "
from sentence_transformers import SentenceTransformer, CrossEncoder
SentenceTransformer('BAAI/bge-m3'); CrossEncoder('BAAI/bge-reranker-v2-m3'); print('ok')"
```

**5.3. Chuyển PDF thành ảnh trang, OCR, lập chỉ mục**

```bash
.venv/bin/python scripts/render_pages.py
.venv/bin/python -m app.ingest data/raw
```

Lệnh thứ hai OCR từng trang (qua engine trong `OCR_BACKEND`), cắt đoạn, tạo vector và ghi vào `data/rag.db`. Kết quả OCR được lưu ở `data/ocr/` nên chạy lại sẽ nhanh. Với Gemini mỗi trang mất vài giây; với PDF vài chục trang, chờ vài phút.

> Tài liệu cũng có thể tải lên sau từ giao diện web (nút **Tải tài liệu lên**), không cần chạy dòng lệnh. Tối đa 20 MB mỗi file, tối đa 200 tài liệu.

## 6. Chọn OCR cho Mac 8 GB

| | Gemini (`OCR_BACKEND=gemini`) | MinerU local (`OCR_BACKEND=mineru`) |
| --- | --- | --- |
| RAM | gần 0 | ≈ 2,5–3 GB, **không chạy cùng API** |
| Tốc độ | vài giây mỗi trang | chậm trên Mac **[chưa kiểm chứng]**; trên GPU NVIDIA ≈ 30 giây |
| Riêng tư | **ảnh từng trang gửi lên Google** | không rời máy |
| Cần | `GEMINI_API_KEY` | môi trường riêng `.venv-mineru` (bên dưới) |

**Hỏi khách trước khi chọn Gemini**: tài liệu ngân hàng nội bộ sẽ được gửi sang Google để OCR. Nếu không chấp nhận, dùng MinerU.

Cài MinerU (chỉ khi cần):

```bash
uv venv --python 3.10 .venv-mineru
uv pip install --python .venv-mineru/bin/python "mineru[core]" transformers accelerate
```

Đặt `OCR_BACKEND=mineru` và `RAG_DEVICE=mps` trong `.env`, **tắt API** (nếu đang chạy), rồi OCR trước:

```bash
RAG_DEVICE=mps .venv-mineru/bin/python scripts/ocr_mineru.py data/ocr data/pages/*.png
.venv/bin/python -m app.ingest data/raw
```

Sau đó mới bật API. PDF có sẵn chữ (không phải ảnh scan) vẫn qua OCR trong thiết kế hiện tại.

## 7. Chạy thử

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Mở `http://localhost:8080` trong trình duyệt. Hỏi thử "Hello" (phải ra câu chào cố định, tức thì) rồi một câu nghiệp vụ có trong tài liệu (phải có trích dẫn `[S1]` bấm được để mở đúng trang PDF). Câu hỏi đầu tiên có thể chậm vì nạp model vào bộ nhớ. Dừng bằng Ctrl+C.

## 8. Tự khởi động cùng máy (launchd)

Tạo file dịch vụ (thay `TENMAY` bằng tên người dùng macOS, kiểm tra bằng `whoami`):

```bash
mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/com.banking-rag.api.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.banking-rag.api</string>
  <key>WorkingDirectory</key><string>/Users/TENMAY/apps/banking-rag</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/caffeinate</string><string>-is</string>
    <string>/Users/TENMAY/apps/banking-rag/.venv/bin/uvicorn</string>
    <string>app.main:app</string><string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8080</string><string>--proxy-headers</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/TENMAY/apps/banking-rag/data/api.log</string>
  <key>StandardErrorPath</key><string>/Users/TENMAY/apps/banking-rag/data/api.log</string>
</dict></plist>
EOF
launchctl load ~/Library/LaunchAgents/com.banking-rag.api.plist
```

`caffeinate -is` giữ máy không ngủ khi dịch vụ đang chạy. Cũng nên vào **System Settings → Battery/Energy** bật "Prevent automatic sleeping when the display is off" và cắm sạc thường trực, nếu không máy ngủ thì web ngừng.

Lệnh quản lý:

```bash
launchctl list | grep banking-rag      # đang chạy chưa
tail -f ~/apps/banking-rag/data/api.log   # xem nhật ký
launchctl unload ~/Library/LaunchAgents/com.banking-rag.api.plist   # dừng
```

Dịch vụ này chạy khi người dùng đăng nhập macOS. Bật tự đăng nhập hoặc để máy luôn ở trạng thái đã đăng nhập.

## 9. Cho người dùng truy cập

Chỉ làm bước này sau khi đặt mật khẩu.

**9.1. Đặt mật khẩu (bắt buộc nếu ra internet)**

Trong `.env`:

```ini
APP_USER=admin
APP_PASSWORD=mat-khau-dai-kho-doan
APP_SECRET=chuoi-ngau-nhien-dai
TRUST_PROXY=1
ALLOW_CUSTOM_ENDPOINTS=0
```

Sinh chuỗi ngẫu nhiên: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Sau đó khởi động lại dịch vụ:

```bash
launchctl unload ~/Library/LaunchAgents/com.banking-rag.api.plist
launchctl load ~/Library/LaunchAgents/com.banking-rag.api.plist
```

Nếu để trống `APP_PASSWORD`, **bất kỳ ai có link đều xem được tài liệu, tải tài liệu lên và tiêu tốn khóa OpenAI của khách**.

**9.2. Chỉ dùng trong mạng nội bộ:** người trong cùng mạng truy cập `http://<IP-Mac>:8080`. Khi đó đổi `--host 127.0.0.1` thành `--host 0.0.0.0` trong file plist. Không đặt mật khẩu thì chỉ nên dùng cách này trong mạng tin cậy.

**9.3. Công khai qua Tailscale Funnel** (miễn phí, có HTTPS, địa chỉ dạng `https://<máy>.<tailnet>.ts.net`):

```bash
brew install --cask tailscale
```

Mở ứng dụng Tailscale, đăng nhập. Vào trang quản trị (login.tailscale.com/admin), bật **HTTPS Certificates** và cho phép **Funnel** cho máy này. Sau đó:

```bash
tailscale funnel --bg 8080
tailscale funnel status
```

Địa chỉ in ra là địa chỉ công khai. Nếu cổng 443 của máy đã dùng cho dịch vụ khác, dùng `tailscale funnel --bg --https=10000 8080`. Tắt công khai: `tailscale funnel reset`.

Nếu lệnh `tailscale` không có trong PATH, dùng `/Applications/Tailscale.app/Contents/MacOS/Tailscale`. **[chưa kiểm chứng]** trên macOS.

Giao diện và API cùng một địa chỉ, nên không cần dịch vụ host riêng.

## 10. Vận hành

**Cập nhật phiên bản mới**

```bash
cd ~/apps/banking-rag && git pull
uv pip install --python .venv/bin/python -r requirements.txt
launchctl unload ~/Library/LaunchAgents/com.banking-rag.api.plist
launchctl load ~/Library/LaunchAgents/com.banking-rag.api.plist
```

**Sao lưu:** copy thư mục `data/` (chứa `rag.db`, PDF gốc, cache OCR) và file `.env`. Dừng dịch vụ trước khi copy để cơ sở dữ liệu không bị ghi dở.

**Đổi model chat:** vào **Cài đặt** trên giao diện, chọn model. Danh sách lấy từ `OPENAI_CHAT_MODEL` trong `.env`. Hai bản mini đạt 13/14 trên bộ đánh giá nội bộ.

**Chi phí OpenAI:** mỗi câu hỏi nghiệp vụ gửi khoảng 3,5–3,7 nghìn token đầu vào và vài trăm token trả lời. Số token từng câu hiện dưới câu trả lời. Đặt giới hạn chi tiêu trong tài khoản OpenAI của khách.

## 11. Xử lý sự cố

| Triệu chứng | Cách xử lý |
| --- | --- |
| `MPS backend out of memory` hoặc máy rất chậm, treo | Đóng ứng dụng khác. Đặt `RAG_DEVICE=cpu` rồi khởi động lại. Không chạy OCR MinerU cùng API. |
| Câu hỏi đầu tiên rất chậm | Bình thường: nạp model lần đầu (≈ 20–60 giây). Các câu sau nhanh hơn. |
| `Sai hoặc thiếu API key` | Kiểm tra `OPENAI_API_KEY` trong `.env`, không có khoảng trắng hay dấu ngoặc thừa. Khởi động lại dịch vụ. |
| Chat chỉ thấy Gemini/OpenAI nhưng không có model | Mục `OPENAI_CHAT_MODEL` sai tên model. |
| `Model phản hồi quá lâu` | Mạng chậm hoặc OpenAI quá tải. Tăng `LLM_TIMEOUT` (mặc định 15 giây) lên 30. |
| Trả lời "Em chưa tìm được căn cứ đủ chắc" | Hệ thống từ chối trả lời khi câu trả lời không qua kiểm tra (thiếu trích dẫn hoặc số liệu không có trong nguồn). Hỏi cụ thể hơn, nêu số hiệu văn bản. |
| Tài liệu tải lên mắc ở trạng thái "đang xử lý" | Xem `data/api.log`. Thường do OCR lỗi (thiếu `GEMINI_API_KEY`) hoặc hết RAM. |
| Không vào được từ máy khác | Dịch vụ đang nghe `127.0.0.1`. Xem mục 9. |
| `launchctl load` báo lỗi | Kiểm tra đường dẫn trong file plist đúng và `whoami` khớp. Xem `data/api.log`. |

## 12. Lưu ý bảo mật cho khách

- Khóa OpenAI/Gemini nằm trong `.env` trên máy. Ai truy cập được máy hoặc thư mục dự án đều đọc được. Bật FileVault và đặt mật khẩu đăng nhập macOS.
- Nếu khóa từng bị gửi qua chat, email hoặc tài liệu, thu hồi và tạo khóa mới.
- Đặt `APP_PASSWORD` trước khi công khai. Giữ `ALLOW_CUSTOM_ENDPOINTS=0` trừ khi cần thật, vì bật nó cho phép người dùng đã đăng nhập khiến máy chủ gọi tới địa chỉ họ nhập.
- Tài liệu OCR bằng Gemini được gửi sang Google. OpenAI nhận đoạn trích tài liệu liên quan đến mỗi câu hỏi.
- Hệ thống chưa có tài khoản theo người dùng: ai biết mật khẩu đều xem được toàn bộ tài liệu.
