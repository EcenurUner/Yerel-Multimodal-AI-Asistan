import tkinter as tk
from tkinter import messagebox, filedialog
from openai import OpenAI
import threading
import os
import base64
import sqlite3
from datetime import datetime
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
import speech_recognition as sr
from gtts import gTTS
from PIL import Image, ImageTk

class YerelAsistanArayuz:
    def __init__(self, pencere):
        self.pencere = pencere
        self.pencere.title("🤖 Gelişmiş Asistanım (SQL Destekli)")
        self.pencere.geometry("560x880") 
        
        # --- RENK PALETİ ---
        self.renk_arka_plan = "#1e242b"
        self.renk_sohbet_bg = "#111827"
        self.renk_metin_kullanici = "#ffffff"
        self.renk_metin_asistan = "#f3f4f6"
        
        self.renk_gri_ana = "#6d6d6e"
        self.renk_lacivert_koyu = "#1e3a8a"
        self.renk_lacivert_acik = "#3b82f6"
        self.renk_giris_bg = "#374151"
        
        self.balon_genislik_siniri = 380 

        self.pencere.configure(bg=self.renk_arka_plan)
        
        # Veritabanı Kurulumu
        self.veritabani_kur()
        
        self.istemci = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama"
        )
        
        self.konusma_gecmisi = [
            {
                "role": "system",
                "content": (
                    "Sen tamamen Türkçe konuşan yapay zeka bir asistansın. "
                    "Cevaplarında ASLA İngilizce veya başka yabancı dilde kelimeler kullanma. "
                    "Cevapların tamamen mantıklı, akıcı, doğal ve dil bilgisine uygun bir Türkçe olmalıdır."
                )
            }
        ]
        
        self.secilen_gorsel_yolu = None
        self.ses_kaydediliyor = False
        self.kayit_verisi = []
        self.gorsel_referanslari = [] 

        self.arayuz_tasarla()
        self.gecmis_mesajlari_yukle()
        
        # Uygulama kapatılırken geçici dosyaları temizleme protokolü
        self.pencere.protocol("WM_DELETE_WINDOW", self.uygulama_kapat)

    def veritabani_kur(self):
        """SQLite veritabanını ve mesajlar tablosunu oluşturur."""
        self.vt_baglanti = sqlite3.connect("asistan_hafiza.db", check_same_thread=False)
        self.vt_imlec = self.vt_baglanti.cursor()
        self.vt_imlec.execute("""
            CREATE TABLE IF NOT EXISTS sohbet_gecmisi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gonderen TEXT,
                mesaj TEXT,
                zaman TEXT
            )
        """)
        self.vt_baglanti.commit()

    def mesaj_vt_kaydet(self, gonderen, mesaj):
        """Mesajları veritabanına yazar."""
        zaman_damgasi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.vt_imlec.execute(
            "INSERT INTO sohbet_gecmisi (gonderen, mesaj, zaman) VALUES (?, ?, ?)",
            (gonderen, mesaj, zaman_damgasi)
        )
        self.vt_baglanti.commit()

    def arayuz_tasarla(self):
        # 1. Üst Panel (Başlık ve Temizle Butonu)
        self.ust_panel = tk.Frame(self.pencere, bg=self.renk_arka_plan)
        self.ust_panel.pack(fill=tk.X, padx=15, pady=10)

        self.baslik_label = tk.Label(
            self.ust_panel, 
            text="Multimodal Yerel Asistan 🎙️📸", 
            font=("Segoe UI", 15, "bold"), 
            bg=self.renk_arka_plan, 
            fg="#60a5fa"
        )
        self.baslik_label.pack(side=tk.LEFT)

        self.temizle_butonu = tk.Button(
            self.ust_panel,
            text="🗑️ Temizle",
            font=("Segoe UI", 9, "bold"),
            bg="#dc2626",
            fg="#ffffff",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.sohbeti_temizle
        )
        self.temizle_butonu.pack(side=tk.RIGHT)

        # 2. Hızlı Soru Butonları Paneli
        self.hizli_soru_frame = tk.Frame(self.pencere, bg=self.renk_arka_plan)
        self.hizli_soru_frame.pack(fill=tk.X, padx=15, pady=(0, 5))

        hizli_sorular = [
            ("👋 Kendini Tanıt", "Merhaba! Kendini kısaca tanıtır mısın?"),
            ("✨ Neler Yapabilirsin?", "Bana hangi konularda yardımcı olabilirsin?"),
            ("💻 Kod Yardımı", "Bana basit bir Python 'Hello World' kodu yazar mısın?")
        ]

        for etiket, soru in hizli_sorular:
            btn = tk.Button(
                self.hizli_soru_frame,
                text=etiket,
                font=("Segoe UI", 8, "bold"),
                bg=self.renk_gri_ana,
                fg="#ffffff",
                activebackground=self.renk_lacivert_koyu,
                activeforeground="#ffffff",
                relief=tk.FLAT,
                cursor="hand2",
                command=lambda s=soru: self.hizli_soru_gonder(s)
            )
            btn.pack(side=tk.LEFT, padx=3, expand=True, fill=tk.X)
        
        # 3. Sohbet Alanı
        self.sohbet_canvas = tk.Canvas(
            self.pencere,
            bg=self.renk_sohbet_bg,
            relief=tk.FLAT,
            highlightthickness=0
        )
        self.sohbet_canvas.pack(padx=15, pady=5, fill=tk.BOTH, expand=True)
        
        self.scrollbar = tk.Scrollbar(
            self.sohbet_canvas, 
            orient="vertical", 
            command=self.sohbet_canvas.yview
        )
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.mesajlar_frame = tk.Frame(self.sohbet_canvas, bg=self.renk_sohbet_bg)
        self.sohbet_canvas.create_window((0, 0), window=self.mesajlar_frame, anchor="nw")
        self.sohbet_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.mesajlar_frame.bind("<Configure>", lambda e: self.sohbet_canvas.configure(scrollregion=self.sohbet_canvas.bbox("all")))
        
        # 4. Görsel Önizleme Etiketi
        self.gorsel_bilgi_label = tk.Label(
            self.pencere,
            text="",
            font=("Segoe UI", 9, "italic"),
            bg=self.renk_arka_plan,
            fg="#9ca3af"
        )
        self.gorsel_bilgi_label.pack(pady=2)

        # 5. Alt Panel (Giriş + Butonlar)
        self.alt_panel = tk.Frame(self.pencere, bg=self.renk_arka_plan)
        self.alt_panel.pack(fill=tk.X, padx=15, pady=8)
        
        self.foto_butonu = tk.Button(
            self.alt_panel,
            text="📷",
            font=("Segoe UI", 12),
            bg=self.renk_gri_ana,
            fg="#ffffff",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.gorsel_sec
        )
        self.foto_butonu.pack(side=tk.LEFT, padx=(0, 5))

        self.mikrofon_butonu = tk.Button(
            self.alt_panel,
            text="🎙️",
            font=("Segoe UI", 12),
            bg=self.renk_gri_ana,
            fg="#ffffff",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.ses_kaydi_baslat_durdur
        )
        self.mikrofon_butonu.pack(side=tk.LEFT, padx=(0, 5))

        self.giris_kutusu = tk.Entry(
            self.alt_panel, 
            font=("Segoe UI", 11), 
            bg=self.renk_giris_bg, 
            fg="#ffffff", 
            insertbackground="#ffffff",
            relief=tk.FLAT
        )
        self.giris_kutusu.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 5))
        self.giris_kutusu.bind("<Return>", lambda event: self.mesaj_gonder())
        
        self.gonder_butonu = tk.Button(
            self.alt_panel, 
            text="Gönder ⚡", 
            font=("Segoe UI", 10, "bold"), 
            bg=self.renk_lacivert_koyu, 
            fg="#ffffff", 
            relief=tk.FLAT, 
            cursor="hand2",
            command=self.mesaj_gonder
        )
        self.gonder_butonu.pack(side=tk.RIGHT, ipadx=10, ipady=5)

    def gecmis_mesajlari_yukle(self):
        """Uygulama açıldığında veritabanındaki mesajları ekrana basar."""
        self.vt_imlec.execute("SELECT gonderen, mesaj FROM sohbet_gecmisi ORDER BY id ASC")
        kayitlar = self.vt_imlec.fetchall()
        
        if kayitlar:
            self.mesaj_ekle("Sistem", "Geçmiş sohbet veritabanından yüklendi. 🗄️", vt_save=False)
            for gonderen, mesaj in kayitlar:
                self.mesaj_ekle(gonderen, mesaj, vt_save=False)
                # LLM sohbet geçmişine de aktaralım
                if gonderen == "Siz":
                    self.konusma_gecmisi.append({"role": "user", "content": mesaj})
                elif gonderen == "Asistan":
                    self.konusma_gecmisi.append({"role": "assistant", "content": mesaj})
        else:
            self.mesaj_ekle("Sistem", "SQL Destekli Yerel Asistan Hazır! 🎙️📸✨", vt_save=False)

    def sohbeti_temizle(self):
        """Sohbeti hem ekrandan hem de veritabanından siler."""
        cevap = messagebox.askyesno("Sohbeti Temizle", "Tüm sohbet geçmişi veritabanından silinecek. Emin misiniz?")
        if cevap:
            self.vt_imlec.execute("DELETE FROM sohbet_gecmisi")
            self.vt_baglanti.commit()
            
            # Ekrana basılan widget'ları temizle
            for child in self.mesajlar_frame.winfo_children():
                child.destroy()
                
            self.konusma_gecmisi = [self.konusma_gecmisi[0]] # Sadece sistem promptu kalsın
            self.mesaj_ekle("Sistem", "Sohbet geçmişi ve veritabanı temizlendi! 🧹", vt_save=False)

    def hizli_soru_gonder(self, soru_metni):
        self.giris_kutusu.delete(0, tk.END)
        self.giris_kutusu.insert(0, soru_metni)
        self.mesaj_gonder()

    def gorsel_sec(self):
        dosya = filedialog.askopenfilename(
            filetypes=[("Resim Dosyaları", "*.png *.jpg *.jpeg *.bmp *.webp")]
        )
        if dosya:
            self.secilen_gorsel_yolu = dosya
            dosya_adi = os.path.basename(dosya)
            self.gorsel_bilgi_label.config(text=f"🖼️ Hazır Görsel: {dosya_adi}")
        else:
            self.secilen_gorsel_yolu = None
            self.gorsel_bilgi_label.config(text="")

    def ses_kaydi_baslat_durdur(self):
        if not self.ses_kaydediliyor:
            self.ses_kaydediliyor = True
            self.kayit_verisi = []
            self.mikrofon_butonu.config(bg="#dc2626", fg="#ffffff")
            self.mesaj_ekle("Sistem", "Sizi dinliyorum... Konuşmanız bitince mikrofona tekrar basın.", vt_save=False)
            threading.Thread(target=self.ses_kaydet, daemon=True).start()
        else:
            self.ses_kaydediliyor = False
            self.mikrofon_butonu.config(bg=self.renk_gri_ana, fg="#ffffff")

    def ses_kaydet(self):
        fs = 16000
        def callback(indata, frames, time, status):
            if self.ses_kaydediliyor:
                self.kayit_verisi.append(indata.copy())
                
        with sd.InputStream(samplerate=fs, channels=1, dtype='int16', callback=callback):
            while self.ses_kaydediliyor:
                sd.sleep(100)
                
        if self.kayit_verisi:
            audio_data = np.concatenate(self.kayit_verisi, axis=0)
            write("gecici_ses.wav", fs, audio_data)
            self.sesi_metne_cevir("gecici_ses.wav")

    def sesi_metne_cevir(self, dosya_yolu):
        r = sr.Recognizer()
        r.energy_threshold = 300
        try:
            with sr.AudioFile(dosya_yolu) as source:
                r.adjust_for_ambient_noise(source, duration=0.3)
                audio = r.record(source)
                metin = r.recognize_google(audio, language="tr-TR")
                self.giris_kutusu.delete(0, tk.END)
                self.giris_kutusu.insert(0, metin)
                self.mesaj_ekle("Sistem", f"Algılanan Ses: '{metin}'", vt_save=False)
        except sr.UnknownValueError:
            self.mesaj_ekle("Sistem", "Ses anlaşılamadı. Lütfen biraz daha yüksek sesle konuşun.", vt_save=False)
        except Exception as e:
            self.mesaj_ekle("Sistem", f"Ses işleme hatası: {e}", vt_save=False)
        finally:
            if os.path.exists(dosya_yolu):
                try:
                    os.remove(dosya_yolu)
                except:
                    pass

    def mesaj_ekle(self, gonderen, mesaj, gorsel_yolu=None, vt_save=True):
        if vt_save and gonderen in ["Siz", "Asistan"]:
            self.mesaj_vt_kaydet(gonderen, mesaj)

        tek_mesaj_frame = tk.Frame(self.mesajlar_frame, bg=self.renk_sohbet_bg)
        tek_mesaj_frame.pack(fill=tk.X, pady=4, padx=10)
        
        if gonderen == "Sistem":
            lbl = tk.Label(
                tek_mesaj_frame, 
                text=f"📢 {mesaj}", 
                font=("Segoe UI", 9, "italic"), 
                fg="#9ca3af", 
                bg=self.renk_sohbet_bg,
                wraplength=self.balon_genislik_siniri
            )
            lbl.pack(anchor="center")
        else:
            is_user = (gonderen == "Siz")
            bg_color = self.renk_lacivert_koyu if is_user else self.renk_gri_ana
            fg_color = self.renk_metin_kullanici if is_user else self.renk_metin_asistan
            anchor = "e" if is_user else "w"
            prefix = "👤 " if is_user else "🤖 "
            
            balon_frame = tk.Frame(tek_mesaj_frame, bg=bg_color, padx=10, pady=6)
            balon_frame.pack(anchor=anchor)
            
            if gorsel_yolu:
                try:
                    img = Image.open(gorsel_yolu)
                    img.thumbnail((200, 200))
                    tk_img = ImageTk.PhotoImage(img)
                    self.gorsel_referanslari.append(tk_img)
                    
                    img_label = tk.Label(balon_frame, image=tk_img, bg=bg_color)
                    img_label.pack(pady=(0, 5))
                except Exception as e:
                    print("Görsel yükleme hatası:", e)

            if mesaj:
                lbl = tk.Label(
                    balon_frame, 
                    text=f"{prefix}{mesaj}", 
                    font=("Segoe UI", 10), 
                    fg=fg_color, 
                    bg=bg_color,
                    wraplength=self.balon_genislik_siniri,
                    justify=tk.LEFT
                )
                lbl.pack()
            
        self.pencere.update_idletasks()
        self.sohbet_canvas.yview_moveto(1.0)

    def mesaj_gonder(self):
        kullanici_mesaji = self.giris_kutusu.get().strip()
        if not kullanici_mesaji and not self.secilen_gorsel_yolu:
            return
            
        self.giris_kutusu.delete(0, tk.END)
        
        gorsel_var = False
        gorsel_b64 = None
        su_anki_gorsel_yolu = self.secilen_gorsel_yolu

        if su_anki_gorsel_yolu:
            gorsel_var = True
            with open(su_anki_gorsel_yolu, "rb") as f:
                gorsel_b64 = base64.b64encode(f.read()).decode('utf-8')
            
            self.mesaj_ekle("Siz", kullanici_mesaji if kullanici_mesaji else "[Görsel Analizi İstendi]", gorsel_yolu=su_anki_gorsel_yolu)
            self.secilen_gorsel_yolu = None
            self.gorsel_bilgi_label.config(text="")
        else:
            self.mesaj_ekle("Siz", kullanici_mesaji)

        self.gonder_butonu.config(state=tk.DISABLED, text="...")
        threading.Thread(target=self.asistandan_yanit_al, args=(kullanici_mesaji, gorsel_var, gorsel_b64), daemon=True).start()
        
    def asistandan_yanit_al(self, mesaj, gorsel_var, gorsel_b64):
        try:
            if gorsel_var:
                soru = mesaj if mesaj else "Bu görselde ne var? Lütfen ayrıntılı bir şekilde Türkçe olarak açıkla."
                cevap = self.istemci.chat.completions.create(
                    model="llava:7b",
                    messages=[
                        {
                            "role": "user",
                            "content": f"{soru}\n\nLütfen cevabını tamamen Türkçe ver.",
                            "images": [gorsel_b64]
                        }
                    ]
                )
            else:
                self.konusma_gecmisi.append({"role": "user", "content": mesaj})
                cevap = self.istemci.chat.completions.create(
                    model="gemma2:2b",
                    messages=self.konusma_gecmisi,
                    temperature=0.3
                )

            asistan_cevabi = cevap.choices[0].message.content
            self.mesaj_ekle("Asistan", asistan_cevabi)
            
            if not gorsel_var:
                self.konusma_gecmisi.append({"role": "assistant", "content": asistan_cevabi})

            self.sesli_oku(asistan_cevabi)
            
        except Exception as e:
            self.mesaj_ekle("Sistem", f"Hata oluştu: {e}", vt_save=False)
        finally:
            self.gonder_butonu.config(state=tk.NORMAL, text="Gönder ⚡")

    def sesli_oku(self, metin):
        def oku():
            try:
                tts = gTTS(text=metin, lang='tr')
                ses_dosyasi = "yanit.mp3"
                tts.save(ses_dosyasi)
                os.system(f'start {ses_dosyasi}')
            except Exception as e:
                pass
        threading.Thread(target=oku, daemon=True).start()

    def uygulama_kapat(self):
        """Kapatılırken veritabanını kapatır ve kalıntı dosyaları siler."""
        try:
            self.vt_baglanti.close()
            if os.path.exists("gecici_ses.wav"):
                os.remove("gecici_ses.wav")
            if os.path.exists("yanit.mp3"):
                os.remove("yanit.mp3")
        except:
            pass
        self.pencere.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    uygulama = YerelAsistanArayuz(root)
    root.mainloop()
