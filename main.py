import os
import requests
from bs4 import BeautifulSoup
import re
from tkinter import *
from tkinter import messagebox
import threading
from io import BytesIO
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import shutil
import subprocess
from distutils.version import LooseVersion

class MangaDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("Manga Downloader")

        self.base_folder = 'mangas'
        if not os.path.exists(self.base_folder):
            os.makedirs(self.base_folder)

        self.downloading = False
        self.chapter_links = []

        self.quality_var = StringVar()
        self.quality_var.set("Alta")

        self.create_ui()

    def create_ui(self):
        # Labels
        label_url = Label(self.root, text="URL del manga:")
        label_name = Label(self.root, text="Nombre del manga:")
        label_quality = Label(self.root, text="Calidad del PDF:")

        label_url.grid(row=0, column=0, sticky="w")
        label_name.grid(row=1, column=0, sticky="w")
        label_quality.grid(row=2, column=0, sticky="w")

        # Entry widgets
        self.entry_url = Entry(self.root, width=50)
        self.entry_name = Entry(self.root, width=50)
        self.entry_url.grid(row=0, column=1, padx=10, pady=5)
        self.entry_name.grid(row=1, column=1, padx=10, pady=5)

        # Quality options
        quality_options = ["Alta", "Media", "Baja"]
        quality_menu = OptionMenu(self.root, self.quality_var, *quality_options)
        quality_menu.grid(row=2, column=1, padx=10, pady=5)

        # Buttons
        self.button_start = Button(self.root, text="Iniciar descarga", command=self.start_download)
        self.button_stop = Button(self.root, text="Detener descarga", command=self.stop_download, state=DISABLED)
        self.button_check_update = Button(self.root, text="Verificar actualizaciones", command=self.check_for_updates)
        self.button_start.grid(row=3, column=0, padx=10, pady=5)
        self.button_stop.grid(row=3, column=1, padx=10, pady=5)
        self.button_check_update.grid(row=3, column=2, padx=10, pady=5)

        # Text area for status updates
        self.status_text = Text(self.root, height=10, width=60)
        self.status_text.grid(row=4, column=0, columnspan=3, padx=10, pady=5)
        self.status_text.config(state=DISABLED)  # Hacer el texto no editable

    def start_download(self):
        manga_url = self.entry_url.get()
        manga_name = self.entry_name.get()
        quality = self.quality_var.get().lower()

        if not manga_url or not manga_name:
            messagebox.showwarning("Advertencia", "Ingresa la URL y el nombre del manga.")
            return

        self.status_text.config(state=NORMAL)
        self.status_text.delete(1.0, END)
        self.status_text.insert(END, "Descargando...\n")

        manga_folder = os.path.join(self.base_folder, manga_name)
        if not os.path.exists(manga_folder):
            os.makedirs(manga_folder)

        self.downloading = True
        self.button_start.config(state=DISABLED)
        self.button_stop.config(state=NORMAL)

        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        try:
            response = session.get(manga_url, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.status_text.insert(END, f"Error al acceder a la URL: {str(e)}\n")
            self.stop_download()
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        self.chapter_links = soup.find_all('a', href=re.compile(r'capítulo|chapter|leer', re.I))

        # Invertir la lista para descargar desde el capítulo 1 en adelante
        self.chapter_links.reverse()

        # Usar un hilo en lugar de un proceso para la descarga
        download_thread = threading.Thread(target=self.download_chapters, args=(manga_folder, quality))
        download_thread.start()

    def download_chapters(self, manga_folder, quality):
        for chapter_link in self.chapter_links:
            if not self.downloading:
                break

            chapter_url = chapter_link['href']
            chapter_name = chapter_link.text.strip()

            # Busca el primer ":" en el nombre del capítulo
            colon_index = chapter_name.find(':')
            if colon_index != -1:
                chapter_name = chapter_name[:colon_index].strip()

            # Elimina caracteres no válidos del nombre del capítulo
            chapter_name = re.sub(r'[\/:*?"<>|]', '', chapter_name)

            # Verificar si el capítulo ya ha sido descargado previamente
            pdf_filename = os.path.join(manga_folder, f'{chapter_name}.pdf')

            # Verificar si ya existe un archivo PDF con el mismo nombre
            if any(
                pdf_name.startswith(f'{chapter_name}.pdf') for pdf_name in os.listdir(manga_folder)
            ):
                self.status_text.insert(END, f"{chapter_name} ya descargado. Saltando...\n")
                continue

            # Excluir capítulos llamados "Primer capítulo" o "Último capítulo"
            if re.search(r'^(primer|último) capítulo$', chapter_name, re.I):
                self.status_text.insert(END, f"Excluyendo {chapter_name}...\n")
                continue

            chapter_folder = os.path.join(manga_folder, chapter_name)

            if not os.path.exists(chapter_folder):
                os.makedirs(chapter_folder)

            session = requests.Session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            try:
                chapter_response = session.get(chapter_url, headers=headers, timeout=10)
                chapter_response.raise_for_status()
            except requests.exceptions.RequestException as e:
                self.status_text.insert(END, f"Error al acceder a {chapter_name}: {str(e)}\n")
                continue

            chapter_soup = BeautifulSoup(chapter_response.text, 'html.parser')
            image_links = chapter_soup.find_all('img', src=True)

            total_images = len(image_links)
            images = []

            def download_image(img_url, img_filename):
                try:
                    img_response = requests.get(img_url, timeout=10)
                    img_response.raise_for_status()

                    # Excluir imágenes pequeñas (ancho o alto menor o igual a 400 píxeles)
                    img = Image.open(BytesIO(img_response.content))
                    img_width, img_height = img.size
                    if img_width <= 400 or img_height <= 400:
                        return

                    img.save(img_filename, 'JPEG', quality=quality_to_pil_quality(quality))
                    images.append(img)
                except (requests.exceptions.RequestException, OSError) as e:
                    self.status_text.insert(END, f"Error al descargar imagen - {str(e)}\n")
                    return
                except ConnectionResetError as cre:
                    self.status_text.insert(END, f"Conexión restablecida al descargar imagen - {str(cre)}\n")
                    return

            threads = []
            for idx, img_link in enumerate(image_links, 1):
                if not self.downloading:
                    break

                img_url = img_link['src']
                img_filename = os.path.join(chapter_folder, f'Image_{idx}.jpg')

                thread = threading.Thread(target=download_image, args=(img_url, img_filename))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            if not self.downloading:
                break

            self.create_pdf(manga_folder, chapter_name, images)
            self.status_text.insert(END, f"{chapter_name} descargado y convertido a PDF.\n")

            # Eliminar la carpeta del capítulo después de convertir a PDF
            shutil.rmtree(chapter_folder)

        self.status_text.insert(END, 'Descarga y conversión a PDF completada.\n')
        self.stop_download()

    def create_pdf(self, manga_folder, chapter_name, images):
        pdf_filename = os.path.join(manga_folder, f'{chapter_name}.pdf')
        c = canvas.Canvas(pdf_filename, pagesize=letter)

        for img in images:
            if not self.downloading:
                break

            img_width, img_height = img.size
            c.setPageSize((img_width, img_height))
            c.drawImage(ImageReader(img), 0, 0, width=img_width, height=img_height)
            c.showPage()

        c.save()

    def stop_download(self):
        self.downloading = False
        self.button_start.config(state=NORMAL)
        self.button_stop.config(state=DISABLED)

    def check_for_updates(self):
        # URL del repositorio de GitHub
        github_url = "https://github.com/Yeyobitz/MangaDownloader"
        
        try:
            # Clonar el repositorio en una carpeta temporal
            temp_folder = os.path.join(os.path.expanduser("~"), "temp_manga_downloader")
            subprocess.run(["git", "clone", github_url, temp_folder])

            # Obtener la versión actual del código
            with open(os.path.join(temp_folder, "version.txt"), "r") as version_file:
                latest_version = version_file.read().strip()

            # Comparar versiones
            current_version = "0.1"  # Cambia esto a la versión actual de tu proyecto
            if LooseVersion(latest_version) > LooseVersion(current_version):
                messagebox.showinfo("Actualización disponible", f"Versión {latest_version} disponible. Puedes actualizar tu programa.")
            else:
                messagebox.showinfo("Sin actualizaciones", "Tu programa está actualizado.")
        except Exception as e:
            messagebox.showerror("Error", f"Error al verificar actualizaciones: {str(e)}")
        finally:
            # Eliminar la carpeta temporal
            shutil.rmtree(temp_folder, ignore_errors=True)

def quality_to_pil_quality(quality):
    if quality == "alta":
        return 95
    elif quality == "media":
        return 75
    elif quality == "baja":
        return 50
    else:
        return 95  # Calidad alta por defecto

if __name__ == "__main__":
    root = Tk()
    app = MangaDownloader(root)
    root.mainloop()
