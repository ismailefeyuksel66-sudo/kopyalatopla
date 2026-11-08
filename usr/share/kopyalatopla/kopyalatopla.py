import sys
import os
import json
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton, QTextEdit,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSplitter, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QPropertyAnimation, QRect
from PyQt5.QtGui import QPixmap, QIcon, QPalette, QColor

CONFIG_DIR = os.path.expanduser("~/.local/share/kopyalatopla")
HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")
THUMB_DIR = os.path.join(CONFIG_DIR, "thumbnails")

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(THUMB_DIR, exist_ok=True)

class DownloadThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, str, str)

    def __init__(self, cmd, title, thumb_url, output_dir):
        super().__init__()
        self.cmd = cmd
        self.title = title
        self.thumb_url = thumb_url
        self.output_dir = output_dir

    def run(self):
        try:
            process = subprocess.Popen(
                self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True, shell=True
            )
            for line in process.stdout:
                self.log_signal.emit(line.strip())
            process.wait()
            
            thumb_path = ""
            if self.thumb_url:
                import urllib.request
                safe_name = "".join([c if c.isalnum() else "_" for c in self.title])[:50]
                thumb_path = os.path.join(THUMB_DIR, f"{safe_name}.jpg")
                try:
                    urllib.request.urlretrieve(self.thumb_url, thumb_path)
                except Exception:
                    thumb_path = ""

            success = process.returncode == 0
            self.finished_signal.emit(success, self.title, thumb_path, self.output_dir)
        except Exception as e:
            self.log_signal.emit(f"Hata: {str(e)}")
            self.finished_signal.emit(False, self.title, "", "")

class KopyalaToplaApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KopyalaTopla - Modern Video İndirici")
        self.resize(1050, 700)
        self.dark_mode = True # Varsayılan şık siyah tema
        
        self.init_ui()
        self.apply_theme()
        self.load_history()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # Splitter kullanarak Ana Panel (Sol) ve Geçmiş Paneli (Sağ) yan yana konumlandırılıyor
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # --- SOL TARAF: İndirme Paneli ---
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Üst Araç Çubuğu (Tema Değiştirici)
        top_bar = QHBoxLayout()
        app_title = QLabel("KopyalaTopla")
        app_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        top_bar.addWidget(app_title)
        top_bar.addStretch()
        
        self.theme_btn = QPushButton("🌙 Siyah Tema")
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_bar.addWidget(self.theme_btn)
        left_layout.addLayout(top_bar)

        # URL Girişi
        url_layout = QVBoxLayout()
        url_layout.addWidget(QLabel("Video URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_layout.addWidget(self.url_input)
        left_layout.addLayout(url_layout)

        # Kaydetme Yolu
        path_layout = QVBoxLayout()
        path_layout.addWidget(QLabel("Kayıt Yeri:"))
        path_hbox = QHBoxLayout()
        self.path_input = QLineEdit(os.path.expanduser("~/Downloads"))
        path_hbox.addWidget(self.path_input)
        browse_btn = QPushButton("Gözat")
        browse_btn.clicked.connect(self.browse_folder)
        path_hbox.addWidget(browse_btn)
        path_layout.addLayout(path_hbox)
        left_layout.addLayout(path_layout)

        # Kalite ve Tür Seçenekleri
        opt_layout = QHBoxLayout()
        
        qual_vbox = QVBoxLayout()
        qual_vbox.addWidget(QLabel("Kalite:"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["4K (2160p)", "2K (1440p)", "1080p", "720p", "480p", "360p", "240p", "144p"])
        qual_vbox.addWidget(self.quality_combo)
        opt_layout.addLayout(qual_vbox)

        type_vbox = QVBoxLayout()
        type_vbox.addWidget(QLabel("İndirme Türü:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Video + Ses", "Sadece Ses (Audio)", "Sadece Video"])
        type_vbox.addWidget(self.type_combo)
        opt_layout.addLayout(type_vbox)

        sub_vbox = QVBoxLayout()
        sub_vbox.addWidget(QLabel("Altyazı:"))
        self.sub_combo = QComboBox()
        self.sub_combo.addItems(["İstemiyorum", "srt", "ass", "vtt", "sub", "ttml", "txt"])
        sub_vbox.addWidget(self.sub_combo)
        opt_layout.addLayout(sub_vbox)

        left_layout.addLayout(opt_layout)

        # Ekstra İçerikler
        extra_layout = QHBoxLayout()
        self.chk_thumb = QCheckBox("Kapak Fotoğrafı")
        self.chk_thumb.setChecked(True)
        self.chk_desc = QCheckBox("Açıklama (.txt)")
        extra_layout.addWidget(self.chk_thumb)
        extra_layout.addWidget(self.chk_desc)
        left_layout.addLayout(extra_layout)

        # --- Animasyonlu Özel Komut Alanı ---
        self.chk_custom = QCheckBox("Özel yt-dlp Komutu Kullan")
        self.chk_custom.toggled.connect(self.animate_custom_box)
        left_layout.addWidget(self.chk_custom)

        # Açılır/Kapanır Konteyner Widget
        self.custom_container = QWidget()
        self.custom_container.setMaximumHeight(0) # Başlangıçta gizli/kapalı
        self.custom_container.setStyleSheet("transition: max-height 0.3s ease;")
        custom_layout_inner = QVBoxLayout(self.custom_container)
        custom_layout_inner.setContentsMargins(0, 0, 0, 0)
        
        self.custom_input = QLineEdit()
        self.custom_input.setPlaceholderText("Örn: yt-dlp -f best --extract-audio ... [URL]")
        custom_layout_inner.addWidget(self.custom_input)
        left_layout.addWidget(self.custom_container)

        # İndir Butonu
        self.download_btn = QPushButton("İndirmeyi Başlat")
        self.download_btn.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
        self.download_btn.clicked.connect(self.start_download)
        left_layout.addWidget(self.download_btn)

        # Log Konsolu
        left_layout.addWidget(QLabel("İşlem Logları:"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        left_layout.addWidget(self.log_box)

        splitter.addWidget(left_container)

        # --- SAĞ TARAF: Geçmiş Paneli (Yanda) ---
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        right_layout.addWidget(QLabel("📜 İndirme Geçmişi"))
        self.history_list = QListWidget()
        self.history_list.setIconSize(QPixmap(90, 50).size())
        right_layout.addWidget(self.history_list)

        clear_history_btn = QPushButton("Geçmişi Temizle")
        clear_history_btn.clicked.connect(self.clear_history)
        right_layout.addWidget(clear_history_btn)

        splitter.addWidget(right_container)
        splitter.setSizes([650, 350]) # Sol taraf geniş, sağ taraf geçmiş paneli

    def animate_custom_box(self, checked):
        # Yumuşak yükseklik animasyonu
        self.anim = QPropertyAnimation(self.custom_container, b"maximumHeight")
        self.anim.setDuration(250) # milisaniye
        if checked:
            self.anim.setStartValue(0)
            self.anim.setEndValue(45)
        else:
            self.anim.setStartValue(45)
            self.anim.setEndValue(0)
        self.anim.start()

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def apply_theme(self):
        if self.dark_mode:
            # Modern Siyah/Koyu Tema Paleti
            self.setStyleSheet("""
                QMainWindow { background-color: #1e1e1e; color: #d4d4d4; }
                QWidget { background-color: #1e1e1e; color: #d4d4d4; font-family: sans-serif; }
                QLabel { color: #d4d4d4; }
                QLineEdit, QComboBox, QTextEdit, QListWidget {
                    background-color: #2d2d2d;
                    color: #ffffff;
                    border: 1px solid #3f3f3f;
                    border-radius: 4px;
                    padding: 4px;
                }
                QPushButton {
                    background-color: #007acc;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                }
                QPushButton:hover { background-color: #0098ff; }
                QPushButton:pressed { background-color: #005999; }
                QCheckBox { color: #d4d4d4; spacing: 5px; }
                QSplitter::handle { background-color: #333333; }
            """)
            self.theme_btn.setText("☀️ Açık Tema")
        else:
            # Ferah Açık Tema Paleti
            self.setStyleSheet("""
                QMainWindow { background-color: #f5f5f5; color: #333333; }
                QWidget { background-color: #f5f5f5; color: #333333; font-family: sans-serif; }
                QLabel { color: #333333; }
                QLineEdit, QComboBox, QTextEdit, QListWidget {
                    background-color: #ffffff;
                    color: #000000;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 4px;
                }
                QPushButton {
                    background-color: #2ecc71;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                }
                QPushButton:hover { background-color: #27ae60; }
                QCheckBox { color: #333333; spacing: 5px; }
                QSplitter::handle { background-color: #dddddd; }
            """)
            self.theme_btn.setText("🌙 Siyah Tema")

    def browse_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Kayıt Klasörü Seç", self.path_input.text())
        if dir_path:
            self.path_input.setText(dir_path)

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Hata", "Lütfen geçerli bir URL girin!")
            return

        output_dir = self.path_input.text().strip()
        height_map = {
            "4K (2160p)": "2160", "2K (1440p)": "1440", "1080p": "1080",
            "720p": "720", "480p": "480", "360p": "360", "240p": "240", "144p": "144"
        }

        if self.chk_custom.isChecked():
            cmd = self.custom_input.text().strip()
            if "{url}" in cmd:
                cmd = cmd.replace("{url}", f'"{url}"')
            else:
                cmd = f"{cmd} \"{url}\""
        else:
            height = height_map.get(self.quality_combo.currentText(), "1080")
            dtype = self.type_combo.currentText()
            
            cmd_parts = [f'yt-dlp -P "{output_dir}"']

            if dtype == "Video + Ses":
                cmd_parts.append(f'-f "bestvideo[height<={height}]+bestaudio/best[height<={height}]"')
            elif dtype == "Sadece Ses (Audio)":
                cmd_parts.append('-x --audio-format mp3')
            elif dtype == "Sadece Video":
                cmd_parts.append(f'-f "bestvideo[height<={height}]"')

            if self.chk_thumb.isChecked():
                cmd_parts.append('--write-thumbnail --embed-thumbnail')

            if self.chk_desc.isChecked():
                cmd_parts.append('--write-description')

            sub_format = self.sub_combo.currentText()
            if sub_format != "İstemiyorum":
                cmd_parts.append(f'--write-subs --sub-langs all --sub-format {sub_format}')

            cmd_parts.append(f'"{url}"')
            cmd = " ".join(cmd_parts)

        self.log_box.clear()
        self.log_box.append(f"Çalıştırılan Komut: {cmd}\n")
        self.download_btn.setEnabled(False)

        try:
            title_process = subprocess.run(f'yt-dlp --get-title --get-thumbnail "{url}"', capture_output=True, text=True, shell=True)
            lines = title_process.stdout.strip().split('\n')
            title = lines[0] if len(lines) > 0 else "İndirilen Video"
            thumb_url = lines[1] if len(lines) > 1 else ""
        except Exception:
            title = "Video"
            thumb_url = ""

        self.thread = DownloadThread(cmd, title, thumb_url, output_dir)
        self.thread.log_signal.connect(self.append_log)
        self.thread.finished_signal.connect(self.download_finished)
        self.thread.start()

    def append_log(self, text):
        self.log_box.append(text)

    def download_finished(self, success, title, thumb_path, output_dir):
        self.download_btn.setEnabled(True)
        if success:
            QMessageBox.information(self, "Başarılı", "İndirme işlemi başarıyla tamamlandı!")
            self.save_history(title, thumb_path, output_dir)
        else:
            QMessageBox.warning(self, "Hata", "İndirme sırasında bir hata oluştu. Logları kontrol edin.")

    def save_history(self, title, thumb_path, output_dir):
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except:
                pass
        
        history.insert(0, {"title": title, "thumb": thumb_path, "path": output_dir})
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)

        self.load_history()

    def load_history(self):
        self.history_list.clear()	
        if not os.path.exists(HISTORY_FILE):
            return
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            
            for item in history:
                title = item.get("title", "Bilinmeyen Video")
                thumb = item.get("thumb", "")
                
                list_item = QListWidgetItem(title)
                if thumb and os.path.exists(thumb):
                    icon = QIcon(thumb)
                    list_item.setIcon(icon)
                self.history_list.addItem(list_item)
        except Exception as e:
            print("Geçmiş yüklenirken hata:", e)

    def clear_history(self):
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
        self.history_list.clear()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = KopyalaToplaApp()
    window.show()
    sys.exit(app.exec_())
