# main.py

import os
import time
import subprocess # FFmpeg komutlarını çalıştırmak için
from google import genai
from elevenlabs.client import ElevenLabs
from elevenlabs import Voice, VoiceSettings
from PIL import Image, ImageDraw, ImageFont # Resme metin eklemek ve resim oluşturmak için

# ----------------------------------------------------------------------
# A. YAPILANDIRMA VE SABİTLER
# ----------------------------------------------------------------------

# 1. API Anahtarlarını ve Sabitleri Yükle (config.py'den varsayalım)
# *Not: config.py dosyanızı oluşturduğunuzdan emin olun.*
from config import GEMINI_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

# Ortam değişkenlerini ayarlayın
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
os.environ["ELEVENLABS_API_KEY"] = ELEVENLABS_API_KEY

# API Client'ları
gemini_client = genai.Client()

from elevenlabs import ElevenLabs # ElevenLabs sınıfını import ettiğinizden emin olun
elevenlabs_client = ElevenLabs(
    api_key=ELEVENLABS_API_KEY
)
# Burç ve tarih sabitleri
BURCLAR = ["Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak", 
           "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"]
HAFTA_TARIHI = "13 - 20 Ekim" # Her hafta güncelleyin

# Altyazı Ayarları
ALT_YAZI_FONT_YOLU = 'arial.ttf' # Sisteminizdeki bir font yolunu belirtin. Örn: 'C:/Windows/Fonts/Arial.ttf'
ALT_YAZI_FONT_SIZE = 60
ALT_YAZI_RENK = 'yellow'

# FFmpeg yolunu belirtmek isterseniz (PATH'te yoksa)
FFMPEG_PATH = 'C:/ffmpeg/bin/ffmpeg.exe' # Eğer PATH'te ise 'ffmpeg' olarak bırakın. Yoksa tam yolu yazın.
# Örn: FFMPEG_PATH = 'C:/ffmpeg/bin/ffmpeg.exe'

# ----------------------------------------------------------------------
# B. GEMINI API (Metin Üretme) - (Değişmedi)
# ----------------------------------------------------------------------

def generate_zodiac_text(burc_adi, hafta):
    """Gemini API kullanarak burç yorumu metni üretir."""
    
    prompt = f"""
    Sen pozitif ve dinamik bir TikTok burç yorumcususun. 
    Lütfen {hafta} haftası için {burc_adi} burcuna özel, 
    TikTok'a uygun, kısa (yaklaşık 150 kelime) bir yorum yaz. 
    Yorumu, videoda alt yazı olarak görüneceği için, 
    kısa ve akılda kalıcı cümleler halinde, 
    her bir cümleyi tek bir satıra yazarak (Paragraf kullanma).
    """
    
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        # Metni temizle ve cümlelere ayır.
        temiz_metin = response.text.replace('\n\n', '\n').strip()
        cümleler = [c.strip() for c in temiz_metin.split('\n') if c.strip()]
        
        # FFmpeg alt yazı süresi hesaplaması için, metni tek bir string olarak döndür.
        return " ".join(cümleler) 
    except Exception as e:
        print(f"Gemini API hatası ({burc_adi}): {e}")
        return None

# ----------------------------------------------------------------------
# C. ELEVENLABS API (Seslendirme) - (Değişmedi)
# ----------------------------------------------------------------------

def generate_audio(text, output_path):
    """ElevenLabs API kullanarak metni ses dosyasına (mp3) çevirir."""
    
    try:
        # 'voice' keyword argümanı yerine doğrudan 'voice_id' kullanmayı deneyelim.
        # Bu, çoğu API'nin metoduyla daha uyumlu olacaktır.
        audio_stream = elevenlabs_client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID, # Voice objesi yerine doğrudan ID
            text=text,
            model_id="eleven_multilingual_v2" # veya "eleven_turbo_v2" gibi uygun model id
        )
        
        # 'convert' metodu bir stream döndürdüğü için bunu doğrudan bir dosyaya yazmalıyız
        with open(output_path, "wb") as f:
            for chunk in audio_stream:
                if chunk:
                    f.write(chunk)
        print(f"✅ Ses dosyası kaydedildi: {output_path}")
        return True
    except Exception as e:
        print(f"ElevenLabs API hatası: {e}")
        import traceback
        traceback.print_exc() # Hatanın detaylarını görmenizi sağlar
        return False


# ----------------------------------------------------------------------
# D. VİDEO OLUŞTURMA (FFmpeg ile Doğrudan Yönetim) - YENİ
# ----------------------------------------------------------------------

def get_audio_duration(audio_path):
    """FFmpeg kullanarak ses dosyasının süresini (saniye) döndürür."""
    try:
        command = [
            FFMPEG_PATH, '-i', audio_path, '-f', 'null', '-'
        ]
        result = subprocess.run(command, capture_output=True, text=True, errors='ignore')
        
        # FFmpeg çıktısında 'Duration: 00:00:XX.XXX' kısmını arıyoruz
        import re
        duration_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})', result.stderr)
        
        if duration_match:
            h, m, s, ms = map(int, duration_match.groups())
            return h * 3600 + m * 60 + s + ms / 100.0
        return None
    except FileNotFoundError:
        print("Hata: FFmpeg bulunamadı. Lütfen FFMPEG_PATH'i veya PATH değişkeninizi kontrol edin.")
        return None
    except Exception as e:
        print(f"Süre hesaplama hatası: {e}")
        return None

def create_tiktok_video(burc_adi, yorum_metni, ses_dosyasi):
    """
    FFmpeg komut satırı aracılığıyla video, ses ve senkronize altyazıları birleştirir.
    """
    
    # 1. Gerekli Süre ve Cümle Hesaplamaları
    video_duration = get_audio_duration(ses_dosyasi)
    if video_duration is None:
        print("Hata: Ses süresi hesaplanamadığı için video oluşturulamıyor.")
        return
        
    cümleler = [c.strip() for c in yorum_metni.split('.') if c.strip()]
    if not cümleler:
        print("Hata: Yorum metni altyazı için parçalanamadı.")
        return

    # Her cümleye eşit süre ayırma (Basit Senkronizasyon)
    cümle_suresi = video_duration / len(cümleler)
    
    # Giriş klibi süresi ve kalan süre
    GIRIS_SURESI = min(2.0, video_duration)
    kalan_sure = video_duration - GIRIS_SURESI
    
    # Resim dosyaları
    giris_resmi = f"resimler/{burc_adi.lower()}_giris.jpg"
    arka_resim1 = f"resimler/arka1.jpg"
    arka_resim2 = f"resimler/arka2.jpg"
    
    # FFmpeg için altyazı filtresini (drawtext) oluşturma
    drawtext_filter = []
    
    # Altyazı renk ve pozisyon ayarları
    renk_hex = f'0x{ALT_YAZI_RENK}' # FFmpeg drawtext için HEX formatına çevir
    y_pozisyon = 1920 - 200 # Ekranın altından 200 piksel yukarı
    
    mevcut_zaman = 0.0
    for i, cumle in enumerate(cümleler):
        baslangic = mevcut_zaman
        bitis = min(mevcut_zaman + cümle_suresi, video_duration)
        mevcut_zaman = bitis
        
        # drawtext komutu: enable='between(t,başlangıç,bitiş)': Altyazının zaman aralığı
        # box=1: Metin kutusu arka planı (okunurluk için)
        text_komutu = (
            f"drawtext=fontfile='{ALT_YAZI_FONT_YOLU}':"
            f"text='{cumle.upper().replace(':', '\\:')}':" # FFmpeg için özel karakter kaçışları
            f"fontsize={ALT_YAZI_FONT_SIZE}:fontcolor={ALT_YAZI_RENK}:"
            f"x=(w-text_w)/2:y={y_pozisyon}:" # Ortaya hizalama
            f"enable='between(t,{baslangic},{bitis})':"
            f"box=1:boxcolor=black@0.6:boxborderw=10"
        )
        drawtext_filter.append(text_komutu)

    # 2. Resim Kliplerini FFmpeg Komutları İçin Hazırlama
    
    # Giriş Resminin Oluşturulması
    input_list = []
    
    # Resim 1 (Giriş) - 0.0'dan GIRIS_SURESI'ne kadar
    input_list.extend([
        '-loop', '1', '-t', str(GIRIS_SURESI), '-i', giris_resmi
    ])
    
    current_time = GIRIS_SURESI
    
    # Resim 2 (Arka 1) - GIRIS_SURESI'nden kalan sürenin yarısına kadar
    if kalan_sure > 0:
        sure1 = kalan_sure / 2
        input_list.extend([
            '-loop', '1', '-t', str(sure1), '-i', arka_resim1
        ])
        current_time += sure1
        
        # Resim 3 (Arka 2) - Kalan son süre
        sure2 = video_duration - current_time
        input_list.extend([
            '-loop', '1', '-t', str(sure2), '-i', arka_resim2
        ])

    # 3. Ana FFmpeg Komutunu Oluşturma
    output_path = f"videolar/{burc_adi.lower()}_haftalik_yorum.mp4"
    
    # Resim girdilerini birleştirme ve boyutlandırma
    # [0:v] [1:v] [2:v] resimlerin index'lerini temsil eder
    # scale=1080:1920:force_original_aspect_ratio=increase: Resmi dikey formata göre yeniden boyutlandır
    # crop=1080:1920: Resmi 1080x1920'ye kırp (TikTok dikey formatı)
    # concat=n=...: Resimleri ard arda birleştir
    
    concat_n = len(input_list) // 4 # -loop, -t, -i, dosya_yolu'ndan dolayı 4'e bölüyoruz
    
    ffmpeg_command = [
        FFMPEG_PATH,
        '-y', # Çıktı dosyasını sormadan üzerine yaz
        *input_list, # Resim girdileri
        '-i', ses_dosyasi, # Ses girdisi
        '-filter_complex',
        (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v0];"
            f"[1:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v1];"
            f"[2:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v2];"
            f"[v0][v1][v2]concat=n={concat_n}:v=1:a=0,format=yuv420p[v_out]"
        ),
        '-map', '[v_out]', # Birleştirilmiş video çıktısını kullan
        '-map', f'{concat_n}:a', # Ses dosyasını kullan (ses girişi, resim girişlerinden sonra gelir)
        '-vf', ','.join(drawtext_filter), # Altyazı filtresini video üzerine uygula
        '-shortest', # Ses süresi bitince videoyu bitir
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-b:a', '192k',
        output_path
    ]

    print(f"🎥 FFmpeg komutu çalıştırılıyor. Lütfen bekleyin...")
    
    try:
        # Komutu çalıştır
        subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
        print(f"✅ Video başarıyla oluşturuldu: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"🚨 FFmpeg HATA: Komut çalıştırılırken hata oluştu.")
        print(f"Hata Çıktısı (stderr):\n{e.stderr}")
        print(f"Komut:\n{' '.join(ffmpeg_command)}")
    except FileNotFoundError:
        print("🚨 HATA: FFmpeg programı sisteminizde bulunamıyor. Lütfen PATH'i veya FFMPEG_PATH değişkenini kontrol edin.")

# ----------------------------------------------------------------------
# E. ANA ÇALIŞTIRMA BLOĞU - (Minimal Değişiklik)
# ----------------------------------------------------------------------

if __name__ == "__main__":
    
    # Gerekli klasörleri oluştur
    os.makedirs('videolar', exist_ok=True)
    os.makedirs('ses_temp', exist_ok=True)
    
    # FFmpeg'in PATH'te olup olmadığını kontrol et (önerilir)
    if FFMPEG_PATH == 'ffmpeg':
        try:
            subprocess.run([FFMPEG_PATH, '-version'], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("-----------------------------------------------------------------")
            print("!!! UYARI: FFmpeg programı bulunamıyor veya PATH'te değil. !!!")
            print("Lütfen FFmpeg'i kurun VEYA FFMPEG_PATH değişkenini güncelleyin.")
            print("-----------------------------------------------------------------")
            exit()
            
    for burc in BURCLAR:
        print(f"\n--- {burc} Burcu İçin İşlem Başlatılıyor ---")
        
        yorum_metni = generate_zodiac_text(burc, HAFTA_TARIHI)
        
        if yorum_metni:
            ses_dosyasi = f"ses_temp/{burc.lower()}.mp3"
            
            if generate_audio(yorum_metni, ses_dosyasi):
                try:
                    create_tiktok_video(burc, yorum_metni, ses_dosyasi)
                except Exception as e:
                    print(f"🚨 Video oluşturma hatası ({burc}): {e}")
            
        time.sleep(1) 
    
    print("\n-------------------------------------------")
    print("Tüm burç yorumları ve videoları hazırlanmıştır!")
    print("-------------------------------------------")