# Cài đặt trên MacBook M2 8 GB (macOS 14 Sonoma)

Từ máy trống đến khi khách dùng được chatbot. **Mac là server duy nhất**: API, giao diện, cơ sở dữ liệu, file tài liệu. Chat dùng OpenAI qua internet. Không cần GPU rời, không cần Docker.

> **Đã chạy thử trên M2 8 GB:** cài môi trường, embedding bằng `mps`, nạp MinerU (rất chậm, xem mục 6). **Chưa kiểm chứng:** launchd (mục 8), Tailscale trên macOS (mục 9). Chỗ chưa chắc có đánh dấu **[chưa kiểm chứng]**.

## Tóm tắt (đường nhanh nhất)

1. Cài công cụ và môi trường Python (mục 1 đến 3).
2. Điền `.env` với **`RAG_DEVICE=mps`** (mục 4). Quên dòng này là lỗi hay gặp nhất: `Torch not compiled with CUDA enabled`.
3. **OCR trên máy có GPU NVIDIA hoặc bằng Gemini, không OCR bằng MinerU trên Mac** (mục 5 và 6). Chép `data/ocr/` hoặc `data/rag.db` sang Mac.
4. Chạy API (mục 7), tự khởi động bằng launchd (mục 8), công khai nếu cần (mục 9).

## 0. Yêu cầu

| Thành phần | Chạy ở đâu | Ghi chú |
| --- | --- | --- |
| API + giao diện web | Mac, cổng 8080 | FastAPI, một tiến trình |
| Embedding `bge-m3`, reranker `bge-reranker-v2-m3` | Mac, GPU Apple (`mps`) | tải ≈ 4,5 GB lần đầu, dùng ≈ 2,5 GB RAM |
| Chat | OpenAI API | cần khóa và internet |
| OCR cho PDF scan | Gemini, MinerU, hoặc máy khác | xem mục 6 |
| Dữ liệu | `data/` trên Mac | SQLite, PDF gốc, cache OCR |

Cần có: macOS 14 trở lên (kiểm tra ở **Apple menu → About This Mac**), ổ trống ≥ 15 GB, khóa OpenAI (`sk-...`; thêm khóa Gemini nếu dùng OCR Gemini), quyền đọc repo `hiimmuc/banking-chatbot-rag` (nhánh `dev`), bộ PDF của khách.

**RAM 8 GB:** macOS và trình duyệt ≈ 4 GB, embedding + reranker ≈ 2,5 GB, gần hết chỗ. Đóng ứng dụng nặng; không chạy OCR MinerU (≈ 2,5-3 GB) cùng lúc với API; không chạy `app.ingest` khi API đang chạy.

## 1. Công cụ nền

Mở **Terminal** (Cmd + Space, gõ `Terminal`).

```bash
xcode-select --install
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Cuối bước Homebrew in hai dòng `echo` và `eval` để thêm vào PATH: chạy đúng hai dòng đó. Rồi:

```bash
brew install git uv
git --version && uv --version && brew --version
```

## 2. Lấy mã nguồn

```bash
mkdir -p ~/apps && cd ~/apps
git clone -b dev git@github.com:hiimmuc/banking-chatbot-rag.git banking-rag
cd banking-rag
```

Báo `Permission denied (publickey)` nghĩa là chưa có khóa SSH GitHub. Dùng HTTPS (GitHub hỏi tài khoản và token): `git clone -b dev https://github.com/hiimmuc/banking-chatbot-rag.git banking-rag`.

Cập nhật về sau: `git pull`, rồi cài lại phụ thuộc nếu `requirements.txt` đổi.

## 3. Môi trường Python

```bash
uv venv --python 3.10 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -c "import torch; print(torch.backends.mps.is_available())"
```

Bước cài mất vài phút. Lệnh cuối phải in `True`; nếu `False`, dùng `RAG_DEVICE=cpu` (chạy được nhưng chậm hơn nhiều). **[chưa kiểm chứng]** Nếu `torch==2.11.0` không có bản cho macOS, đổi dòng đó trong `requirements.txt` thành `torch` rồi cài lại.

## 4. Cấu hình `.env`

```bash
cp .env.example .env && chmod 600 .env && open -e .env
```

`.env.example` che giá trị nhạy cảm bằng `***REMOVED***`; điền giá trị thật vào `.env`. **Sửa dòng có sẵn, không thêm dòng trùng** (`.env.example` mặc định `RAG_DEVICE=cuda`). Kiểm tra bằng `grep RAG_DEVICE .env`.

```ini
CHAT_PROVIDER=openai
OPENAI_API_KEY=sk-...                          # khóa của khách
OPENAI_CHAT_MODEL=gpt-4.1-mini,gpt-5.4-mini    # mục đầu là mặc định
QWEN_BASE_URL=                                 # để trống: ẩn lựa chọn Qwen local
GEMINI_API_KEY=                                # chỉ điền nếu dùng OCR Gemini

OCR_BACKEND=gemini                             # gemini hoặc mineru (mục 6)
RAG_DEVICE=mps                                 # cpu nếu mps không dùng được

ORG_NAME=Tên đơn vị                            # thương hiệu: tùy chọn
AUTHOR_INFO=Họ tên - Đơn vị
BRAND_LOGO_HEADER=                             # png/webp/jpg, không dùng SVG
BRAND_LOGO_FOOTER_LIGHT=
BRAND_LOGO_FOOTER_DARK=

APP_USER=admin
APP_PASSWORD=                                  # BẮT BUỘC đặt nếu mở ra internet (mục 9)
ALLOW_CUSTOM_ENDPOINTS=0
```

- Logo: đặt file vào `private/brand/`, ghi đường dẫn như `BRAND_LOGO_HEADER=private/brand/logo.png`. Báo `ignored: not a png/webp/jpg` nghĩa là file không phải ảnh thật; kiểm tra bằng `file private/brand/*`.
- Giá trị trống, `***REMOVED***` hoặc bắt đầu bằng `your-` được coi là chưa đặt.
- **Không gửi `.env` qua chat hay email.** File đã nằm trong `.gitignore`.

## 5. Nạp tài liệu

Có bốn cách đưa tài liệu vào. Chọn theo tình huống:

| Cách | Khi nào | Lệnh |
| --- | --- | --- |
| Giao diện web | Dùng thường ngày | nút **Tải tài liệu lên** (≤ 20 MB, ≤ 200 tài liệu) |
| Dòng lệnh | Giao diện lỗi, nạp hàng loạt | xem dưới |
| `curl` | Script, API đang chạy | `curl -u admin:MATKHAU -F "file=@x.pdf" http://localhost:8080/api/documents` |
| Chép từ máy khác | OCR trên máy GPU rồi mang sang | xem mục 6 |

**Dòng lệnh** (dừng API trước để đỡ tốn RAM):

```bash
mkdir -p data/raw && cp /đường/dẫn/*.pdf data/raw/
.venv/bin/python -c "
from sentence_transformers import SentenceTransformer, CrossEncoder
SentenceTransformer('BAAI/bge-m3'); CrossEncoder('BAAI/bge-reranker-v2-m3'); print('ok')"   # tải model trước, ≈ 4,5 GB
.venv/bin/python -m app.ingest data/raw
```

`app.ingest` OCR (theo `OCR_BACKEND`), cắt đoạn, tạo vector, ghi `data/rag.db`; bỏ qua file ẩn như `.DS_Store`. Chạy lại an toàn: trang đã có cache `data/ocr/` không OCR lại, đoạn cũ bị thay chứ không nhân đôi.

- Tên file nên bắt đầu bằng mã văn bản (`66CNTI_...pdf`); mã này làm ID tài liệu. Tên khác nhận ID băm.
- `scripts/render_pages.py` không cần thiết (ingest tự render ảnh trang); file có tên không bắt đầu bằng mã bị bỏ qua.
- Nếu khởi động lại API giữa lúc đang xử lý, tài liệu dở dang tự được làm tiếp khi API lên lại.

Trong giao diện, mỗi tài liệu đang xử lý có thanh tiến trình theo từng bước (OCR theo trang, rồi lập chỉ mục).

## 6. OCR: chọn cách nào

| | Gemini | MinerU trên Mac | MinerU trên máy GPU |
| --- | --- | --- | --- |
| Đặt | `OCR_BACKEND=gemini` | `OCR_BACKEND=mineru` | chạy ở máy khác |
| Tốc độ | vài giây mỗi trang | **≈ 7 phút mỗi trang** (đo trên M2 8 GB; 84 trang ≈ 10 giờ) | ≈ 30 giây mỗi trang (RTX 4060) |
| RAM Mac | gần 0 | ≈ 2,5-3 GB, **không chạy cùng API** | 0 |
| Riêng tư | **ảnh từng trang gửi lên Google** | không rời máy | không rời máy |
| Toạ độ khung chữ | không | có | có |

**Khuyến nghị:** OCR ở máy có GPU NVIDIA rồi chép sang Mac. Nếu tài liệu không được gửi ra ngoài thì đây là cách duy nhất vừa nhanh vừa riêng tư. Nếu khách chấp nhận gửi ảnh lên Google, dùng Gemini (**hỏi khách trước**).

**Chép kết quả từ máy GPU sang Mac:**

```bash
# trên máy GPU: nén cache OCR và (tùy chọn) cả cơ sở dữ liệu đã ingest
cd data && zip -r ocr.zip ocr && zip rag-db.zip rag.db      # nên dừng API trước khi nén rag.db
# trên Mac, trong thư mục banking-rag, sau khi đã đặt PDF vào data/raw/
unzip -o ocr.zip -d data/
.venv/bin/python -m app.ingest data/raw        # bỏ qua OCR, chỉ tạo vector (vài phút)
```

Hoặc chép luôn `rag.db` để khỏi ingest: dừng API, xóa `data/rag.db*` cũ, `unzip -o rag-db.zip -d data/`, đặt PDF vào `data/raw/`. Cần cùng `EMBED_MODEL` ở hai máy. Đường dẫn file trong DB là tương đối nên chạy được khi API chạy từ thư mục `banking-rag`.

**Cài MinerU trên Mac (chỉ khi thật sự cần):**

```bash
uv venv --python 3.10 .venv-mineru
uv pip install --python .venv-mineru/bin/python "mineru[core]" transformers accelerate
```

Không chạy lệnh `--reinstall torch ... cu128` của README (dành cho NVIDIA). Model MinerU (≈ 2,3 GB) tự tải lần đầu. Cần `RAG_DEVICE=mps` và bản mã có sửa nạp model (nạp CPU rồi chuyển sang `mps`), nếu không sẽ báo `segmentation fault` ở `Loading weights`. Tài liệu upload qua giao diện cũng đi qua MinerU này; mỗi tài liệu có thể mất hàng giờ.

## 7. Chạy thử

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Mở `http://localhost:8080`. Hỏi "Hello" (phải ra câu chào cố định, tức thì), rồi một câu nghiệp vụ có trong tài liệu: câu trả lời có trích dẫn `[S1]`; bấm vào mở popup ảnh trang PDF cùng văn bản OCR với đoạn được trích tô vàng. Câu đầu tiên chậm hơn vì nạp model (≈ 20-60 giây). Dừng bằng Ctrl+C.

**Thư viện tài liệu** (cột trái): tích/bỏ tích để chọn tài liệu dùng khi trả lời (lưu trong trình duyệt); bấm tên để xem tài liệu từng trang; ✕ để xóa (xóa chỉ mục, cache OCR, bản tải lên; file tự chép vào `data/raw/` được giữ lại nên `app.ingest` sau sẽ nạp lại); kéo mép phải để đổi độ rộng; nút **Thư viện** trên header để ẩn/hiện. **Cài đặt** có chọn model, phong cách trả lời và cỡ chữ.

## 8. Tự khởi động cùng máy (launchd)

Thay `TENMAY` bằng tên người dùng macOS (`whoami`):

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

`caffeinate -is` giữ máy không ngủ khi dịch vụ chạy. Vào **System Settings → Battery → Options** bật "Prevent automatic sleeping on power adapter when the display is off" và cắm sạc thường trực, nếu không máy ngủ thì web ngừng. Dịch vụ chạy khi người dùng đăng nhập; bật tự đăng nhập hoặc để máy luôn đăng nhập.

```bash
launchctl list | grep banking-rag                                     # đang chạy chưa
tail -f ~/apps/banking-rag/data/api.log                               # nhật ký
launchctl unload ~/Library/LaunchAgents/com.banking-rag.api.plist     # dừng (load để chạy lại)
```

## 9. Cho người dùng truy cập

Chỉ làm sau khi đặt mật khẩu. Trong `.env`:

```ini
APP_USER=admin
APP_PASSWORD=mat-khau-dai-kho-doan
APP_SECRET=chuoi-ngau-nhien-dai      # python3 -c "import secrets; print(secrets.token_urlsafe(32))"
TRUST_PROXY=1
ALLOW_CUSTOM_ENDPOINTS=0
```

Rồi khởi động lại dịch vụ (`unload` rồi `load`). Để trống `APP_PASSWORD` thì **ai có link đều xem và xóa được tài liệu, tải lên, và tiêu tốn khóa OpenAI của khách**.

- **Mạng nội bộ:** đổi `--host 127.0.0.1` thành `--host 0.0.0.0` trong plist; người cùng mạng vào `http://<IP-Mac>:8080`. Không đặt mật khẩu thì chỉ dùng trong mạng tin cậy.
- **Công khai qua Tailscale Funnel** (miễn phí, HTTPS, `https://<máy>.<tailnet>.ts.net`):

  ```bash
  brew install --cask tailscale
  ```

  Mở ứng dụng Tailscale, đăng nhập; trong trang quản trị (login.tailscale.com/admin) bật **HTTPS Certificates** và **Funnel** cho máy này. Sau đó:

  ```bash
  tailscale funnel --bg 8080
  tailscale funnel status
  ```

  Cổng 443 đã bận thì dùng `tailscale funnel --bg --https=10000 8080`. Tắt: `tailscale funnel reset`. Nếu không có lệnh `tailscale`, dùng `/Applications/Tailscale.app/Contents/MacOS/Tailscale`. **[chưa kiểm chứng]** trên macOS.
- **Địa chỉ ngắn `*.workers.dev`:** xem `deploy/worker/` trong README (Worker chuyển tiếp tới địa chỉ Funnel). Lỗi `525` ở địa chỉ này thường chỉ là lỗi thoáng qua của Funnel; thử lại sau ít phút.

Giao diện và API cùng một địa chỉ nên không cần host riêng.

## 10. Vận hành

- **Cập nhật:** `cd ~/apps/banking-rag && git pull`, `uv pip install --python .venv/bin/python -r requirements.txt`, rồi `unload`/`load` dịch vụ. File tĩnh (`web/`) chỉ cần tải lại trang.
- **Sao lưu:** dừng dịch vụ, copy `data/` (`rag.db`, PDF, cache OCR) và `.env`.
- **Đổi model chat:** **Cài đặt** trên giao diện; danh sách lấy từ `OPENAI_CHAT_MODEL`.
- **Chi phí:** mỗi câu hỏi gửi khoảng 3,5-3,7 nghìn token vào và vài trăm token ra; số token hiện dưới câu trả lời. Đặt giới hạn chi tiêu trong tài khoản OpenAI của khách.

## 11. Xử lý sự cố

| Triệu chứng | Cách xử lý |
| --- | --- |
| `Torch not compiled with CUDA enabled` | `.env` còn `RAG_DEVICE=cuda`. Sửa thành `mps` (`sed -i '' 's/^RAG_DEVICE=.*/RAG_DEVICE=mps/' .env`) và chạy lại. |
| `segmentation fault` ở `Loading weights` (MinerU) | Dùng bản mã mới nhất (nạp model lên CPU rồi chuyển `mps`); nếu vẫn lỗi, OCR bằng Gemini hoặc ở máy khác. |
| OCR "treo" nhiều giờ | MinerU trên Mac ≈ 7 phút mỗi trang, không phải treo. Dừng (Ctrl+C) và dùng mục 6. |
| `MPS backend out of memory` hoặc máy rất chậm | Đóng ứng dụng khác; `RAG_DEVICE=cpu`; không chạy MinerU hoặc `app.ingest` cùng API. Xem Memory Pressure trong Activity Monitor. |
| Câu hỏi đầu tiên rất chậm | Bình thường (nạp model 20-60 giây). Các câu sau nhanh hơn. |
| Tài liệu kẹt ở trạng thái "đang xử lý" | Khởi động lại API: tài liệu dở dang tự làm tiếp. Thiếu file gốc thì chuyển "Lỗi", tải lại. Xem `data/api.log`. |
| `Sai hoặc thiếu API key` | Kiểm tra `OPENAI_API_KEY` trong `.env`, không có khoảng trắng hay ngoặc thừa; khởi động lại. |
| Chat không có model | `OPENAI_CHAT_MODEL` sai tên model. |
| `Model phản hồi quá lâu` | Mạng chậm hoặc OpenAI quá tải; tăng `LLM_TIMEOUT` (mặc định 15) lên 30. |
| "Em chưa tìm được căn cứ đủ chắc" | Câu trả lời không qua kiểm tra (thiếu trích dẫn, số không có trong nguồn). Hỏi cụ thể hơn, nêu số hiệu văn bản. Kiểm tra các tài liệu liên quan đang được tích. |
| Bấm trích dẫn không mở được | Cập nhật bản mã mới (đã sửa lỗi header) và khởi động lại API. |
| Không vào được từ máy khác | Dịch vụ đang nghe `127.0.0.1`; xem mục 9. |
| `launchctl load` báo lỗi | Kiểm tra đường dẫn trong plist và `whoami`; xem `data/api.log`. |

## 12. Bảo mật

- Khóa OpenAI/Gemini nằm trong `.env`; ai truy cập được máy hoặc thư mục dự án đều đọc được. Bật FileVault và đặt mật khẩu đăng nhập macOS.
- Khóa từng bị gửi qua chat, email hoặc tài liệu thì thu hồi và tạo khóa mới.
- Đặt `APP_PASSWORD` trước khi công khai. Giữ `ALLOW_CUSTOM_ENDPOINTS=0` trừ khi cần thật, vì bật nó cho phép người dùng đã đăng nhập khiến máy chủ gọi tới địa chỉ họ nhập.
- OCR bằng Gemini gửi ảnh trang sang Google; OpenAI nhận đoạn trích liên quan đến mỗi câu hỏi.
- Chưa có tài khoản theo người dùng: ai biết mật khẩu đều xem, tải lên và xóa được mọi tài liệu.
