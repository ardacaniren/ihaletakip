# İhale Takip Panosu (Konya İSM prototipi)

- `scraper.py`: Konya İl Sağlık Müdürlüğü ana sayfasını okur, yeni ilanları puanlar, `data.json` yazar.
- `index.html`: `data.json` dosyasını kart olarak gösterir (filtre, 70+ seçeneği, durum seçici).
- `.github/workflows/scrape.yml`: scraper'ı 6 saatte bir çalıştırıp `data.json` dosyasını repoya yazar.

Yerelde deneme: `pip install -r requirements.txt`, `python scraper.py`, `python -m http.server`, sonra http://localhost:8000
Durum seçimleri (Yeni fırsat, Teklif aşaması...) şimdilik her kişinin kendi tarayıcısında saklanır.
