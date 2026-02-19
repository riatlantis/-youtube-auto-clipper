# YouTube Auto Clipper (Trending -> Shorts)

Aplikasi ini mengambil daftar video YouTube yang sedang trending, lalu membuat klip pendek vertikal (9:16) secara otomatis untuk format short video.

## Fitur
- Ambil video trending berdasarkan `region` dan `category`.
- Pilih beberapa video sekaligus.
- Potong otomatis jadi beberapa klip per video.
- Prioritas segmen dari subtitle (kata-kata "hook"), fallback ke potongan merata jika subtitle tidak ada.
- Output MP4 siap upload ke short-form platform.

## Prasyarat
- Python 3.10+
- `ffmpeg` dan `ffprobe` tersedia di PATH
- API key YouTube Data API v3

## Install
```powershell
cd C:\Users\cep_c\youtube-auto-clipper
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Copy env:
```powershell
Copy-Item .env.example .env
```

Isi `YOUTUBE_API_KEY` di file `.env`.

## Jalankan
```powershell
cd C:\Users\cep_c\youtube-auto-clipper
.\.venv\Scripts\activate
streamlit run app\app.py
```

## Deploy ke Streamlit Community Cloud
1. Push project ini ke GitHub.
2. Di Streamlit Cloud pilih:
- Repository: repo GitHub Anda
- Branch: `main`
- Main file path: `app/app.py`
3. Tambahkan secrets di menu App Settings -> Secrets:
```toml
YOUTUBE_API_KEY="isi_api_key_anda"
YOUTUBE_REGION="ID"
YOUTUBE_CATEGORY_ID="24"
```
4. Redeploy app.

## Alur Pakai
1. Isi API key.
2. Klik `Load Trending`.
3. Pilih video.
4. Klik `Generate Clips`.
5. Ambil hasil di folder `output/`.

## Catatan penting
- Hormati hak cipta, lisensi konten, dan kebijakan YouTube saat melakukan reupload.
- Untuk hasil lebih bagus, bisa ditambah subtitle hardcode/face tracking pada versi berikutnya.
