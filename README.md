# Đọc Sách VieNeu (PC)

Ứng dụng Windows đọc sách thành tiếng bằng **VieNeu-TTS v3 Turbo** (engine chính chủ của Phạm Nguyễn Ngọc Bảo, chạy offline trên máy):

- Thêm sách **PDF / EPUB / TXT** vào thư viện (sách được sao chép vào `%APPDATA%\VieNeuReader`, mở lại là đọc tiếp đúng đoạn đang dở).
- Bấm **Nghe**: engine tổng hợp trước 2 đoạn trong lúc phát đoạn hiện tại, tô sáng câu đang đọc, tự cuộn theo.
- Bấm vào bất kỳ câu nào trong trang để đọc từ câu đó.
- Chọn giọng trong danh sách giọng có sẵn của VieNeu (3 miền), tốc độ 0.25×–3×.
- **Đọc truyện web**: dán link 1 chương truyện (các web truyện thông thường) → app tự bóc nội dung chương, nghe xong bấm **Tải chương tiếp** để app tự lần theo link chương sau và nối vào sách. Trang nào nạp bằng JavaScript hoặc chặn bot thì không bóc được.
- **Web truyện nhúng (Sáng Tác Việt...)**: tab **Web truyện** là một trình duyệt ngay trong app — đăng nhập 1 lần (app tự nhớ cookie), chọn truyện, mở chương như trên trình duyệt, bấm **Đọc chương này** → VieNeu đọc; hết chương app **tự bấm nút chương tiếp trên trang** và đọc tiếp (có ô tắt/mở chế độ tự qua chương).
- Chất lượng: **int8** (nhanh, nhẹ) hoặc **fp32** (xịn nhất — đúng nghĩa "bản xịn nhất": backbone độ chính xác đầy đủ).
- Cache âm thanh theo nội dung: mở lại sách không phải tổng hợp lại từ đầu.

Lần đầu bấm Nghe, engine tải model từ HuggingFace (cần mạng, vài trăm MB) — các lần sau chạy hoàn toàn offline.

## Chạy bản đóng gói
Tải `VieNeuReader-Windows.zip` từ Releases, giải nén, chạy `VieNeuReader.exe`. Không cần cài Python.

## Chạy từ source
`run.bat` (tự tạo venv + cài thư viện + mở app), hoặc:
```
pip install -r requirements.txt
python run_app.py
```

## Kiểm tra engine
```
python run_app.py --selftest report.json
```
Nạp VieNeu int8, tổng hợp thử 1 câu, ghi báo cáo (thời gian nạp, số giọng, RTF) vào report.json.
