import sys
import os
import math
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QSpinBox, QPushButton, QColorDialog,
    QComboBox, QFileDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QMessageBox
)
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QKeyEvent
from PySide6.QtCore import Qt, QPoint, QRect, QObject, QEvent

from PIL import Image, ImageFilter, ImageEnhance, ImageFont, ImageDraw, ImageOps

SUPPORTED_EXT = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"]

def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    data = img.tobytes("raw", img.mode)
    qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888 if img.mode == "RGBA" else QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)

def list_system_font_files():
    paths = []
    plat = sys.platform
    if plat.startswith("win"):
        base = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
        paths.extend([os.path.join(base, p) for p in os.listdir(base)]) if os.path.isdir(base) else None
    elif plat == "darwin":
        for base in ["/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]:
            if os.path.isdir(base):
                paths.extend([os.path.join(base, p) for p in os.listdir(base)])
    else:
        for base in ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts")]:
            for root, _, files in os.walk(base):
                for f in files:
                    paths.append(os.path.join(root, f))
    font_map = {}
    for p in paths:
        name = os.path.basename(p).lower()
        font_map[name] = p
    return font_map

FONT_FILES = list_system_font_files()

def find_font(preferred_names, size):
    for name in preferred_names:
        key = name.lower().replace(" ", "")
        # try exact/contains match among available files
        candidates = [v for k, v in FONT_FILES.items() if key in k.replace(" ", "")]
        if candidates:
            try:
                return ImageFont.truetype(candidates[0], size)
            except Exception:
                continue
    # generic fallbacks
    for generic in ["arial.ttf", "DejaVuSans.ttf", "verdana.ttf", "Helvetica.ttf", "FreeSans.ttf"]:
        for k, v in FONT_FILES.items():
            if generic.lower() in k:
                try:
                    return ImageFont.truetype(v, size)
                except Exception:
                    continue
    try:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()

STYLE_FONT_PREFS = {
    "None": ["Arial", "DejaVu Sans", "Verdana", "Helvetica"],
    "Epic": ["Impact", "Anton", "Bebas Neue", "Arial Black", "DejaVu Sans"],
    "Noir": ["Georgia", "Times New Roman", "DejaVu Serif", "Merriweather"],
    "Fancy": ["Pacifico", "Brush Script", "Lobster", "Segoe Script", "Gabriola", "DejaVu Sans"],
    "Cyberpunk": ["Orbitron", "Eurostile", "Agency FB", "Bank Gothic", "Audiowide", "DejaVu Sans"],
    "Phonk": ["Futura", "Avenir", "Montserrat", "Poppins", "Gotham", "DejaVu Sans"],
    "Tech": ["Consolas", "Courier New", "Inconsolata", "DejaVu Sans Mono", "SF Mono", "DejaVu Sans"],
}

def apply_style(background: Image.Image, style_name: str) -> Image.Image:
    img = background.convert("RGB")
    if style_name == "None":
        return img
    if style_name == "Epic":
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        img = img.filter(ImageFilter.GaussianBlur(radius=3))
    elif style_name == "Noir":
        img = ImageOps.grayscale(img).convert("RGB")
    elif style_name == "Fancy":
        img = ImageEnhance.Color(img).enhance(1.6)
    elif style_name == "Cyberpunk":
        r, g, b = img.split()
        img = Image.merge("RGB", (b, g, r))
        img = ImageEnhance.Color(img).enhance(1.2)
        img = ImageEnhance.Contrast(img).enhance(1.1)
    elif style_name == "Phonk":
        img = ImageEnhance.Brightness(img).enhance(0.75)
        overlay = Image.new("RGB", img.size, (40, 0, 60))
        img = Image.blend(img, overlay, 0.2)
        img = ImageEnhance.Contrast(img).enhance(1.1)
    elif style_name == "Tech":
        img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=200, threshold=3))
    return img

def wrap_text(text, font, draw, max_width):
    if not text:
        return []
    words = text.split()
    lines = []
    line = ""
    for w in words:
        test = w if line == "" else line + " " + w
        bbox = draw.textbbox((0, 0), test, font=font, align="left")
        if bbox[2] - bbox[0] <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines

def measure_multiline(lines, font, draw, line_spacing):
    width = 0
    height = 0
    line_heights = []
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font, align="left")
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        width = max(width, w)
        line_heights.append(h)
    if line_heights:
        height = sum(line_heights) + line_spacing * (len(line_heights) - 1)
    else:
        height = 0
    return width, height, line_heights

class PreviewLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.scale = 1.0
        self.ox = 0
        self.oy = 0
        self.dragging = False
        self.drag_show_box = False
        self.text_bbox_img_coords = QRect(0, 0, 0, 0)

    def set_viewport_transform(self, scale, ox, oy):
        self.scale = scale
        self.ox = ox
        self.oy = oy
        self.update()

    def set_text_bbox(self, rect: QRect):
        self.text_bbox_img_coords = rect
        self.update()

    def map_to_img(self, pos: QPoint):
        x = (pos.x() - self.ox) / self.scale
        y = (pos.y() - self.oy) / self.scale
        return QPoint(int(round(x)), int(round(y)))

    def map_rect_to_view(self, rect: QRect):
        x = rect.x() * self.scale + self.ox
        y = rect.y() * self.scale + self.oy
        w = rect.width() * self.scale
        h = rect.height() * self.scale
        return QRect(int(x), int(y), int(w), int(h))

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.drag_show_box and self.text_bbox_img_coords.width() > 0:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            view_rect = self.map_rect_to_view(self.text_bbox_img_coords)
            pen = QPen(QColor(255, 255, 255, 180))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawRect(view_rect)
            painter.end()

class QuoteStudio(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quote Studio")
        self.base_image = Image.new("RGB", (1200, 800), (40, 40, 40))
        self.filtered_bg = self.base_image.copy()
        self.result_image = self.base_image.copy()
        self.current_style = "None"
        self.text_color = (255, 255, 255)
        self.font_size = 64
        self.quote = ""
        self.author = ""
        self.text_pos = [60, 60]  # in image coords (top-left of text block)
        self.margin_ratio = 0.05
        self.last_pixmap = None

        self.preview = PreviewLabel()
        self.preview.setMinimumSize(640, 400)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.drag_show_box = False

        # Controls
        self.quote_input = QLineEdit()
        self.quote_input.setPlaceholderText("Enter quote text...")
        self.author_input = QLineEdit()
        self.author_input.setPlaceholderText("Enter author (optional)")

        self.font_spin = QSpinBox()
        self.font_spin.setRange(10, 200)
        self.font_spin.setValue(self.font_size)

        self.color_btn = QPushButton("Pick Text Color")
        self.style_combo = QComboBox()
        for s in ["None", "Epic", "Noir", "Fancy", "Cyberpunk", "Phonk", "Tech"]:
            self.style_combo.addItem(s)

        self.load_btn = QPushButton("Load Image")
        self.save_btn = QPushButton("Save Output")

        # Layout
        g = QGridLayout()
        g.addWidget(QLabel("Quote:"), 0, 0)
        g.addWidget(self.quote_input, 0, 1, 1, 3)
        g.addWidget(QLabel("Author:"), 1, 0)
        g.addWidget(self.author_input, 1, 1, 1, 3)
        g.addWidget(QLabel("Font size:"), 2, 0)
        g.addWidget(self.font_spin, 2, 1)
        g.addWidget(QLabel("Style:"), 2, 2)
        g.addWidget(self.style_combo, 2, 3)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.color_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.load_btn)
        btn_row.addWidget(self.save_btn)

        main = QVBoxLayout(self)
        main.addWidget(self.preview, stretch=1)
        main.addLayout(g)
        main.addLayout(btn_row)

        # Signals
        self.quote_input.textChanged.connect(self.on_text_change)
        self.author_input.textChanged.connect(self.on_text_change)
        self.font_spin.valueChanged.connect(self.on_font_change)
        self.color_btn.clicked.connect(self.on_pick_color)
        self.style_combo.currentTextChanged.connect(self.on_style_change)
        self.load_btn.clicked.connect(self.on_load_image)
        self.save_btn.clicked.connect(self.on_save_image)

        # Mouse events for dragging
        self.preview.installEventFilter(self)

        # Initial render
        self.recompute()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.preview:
            if event.type() == QEvent.MouseButtonPress:
                return self.on_mouse_press(event)
            elif event.type() == QEvent.MouseMove:
                return self.on_mouse_move(event)
            elif event.type() == QEvent.MouseButtonRelease:
                return self.on_mouse_release(event)
            elif event.type() == QEvent.Resize:
                self.update_preview_pixmap()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, e: QKeyEvent):
        step = 10 if (e.modifiers() & Qt.ShiftModifier) else 1
        changed = False
        if e.key() == Qt.Key_Left:
            self.text_pos[0] -= step
            changed = True
        elif e.key() == Qt.Key_Right:
            self.text_pos[0] += step
            changed = True
        elif e.key() == Qt.Key_Up:
            self.text_pos[1] -= step
            changed = True
        elif e.key() == Qt.Key_Down:
            self.text_pos[1] += step
            changed = True
        if changed:
            self.clamp_text_within()
            self.recompute()
        else:
            super().keyPressEvent(e)

    def on_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            img_pt = self.preview.map_to_img(event.position().toPoint())
            if self.point_in_text_bbox(img_pt.x(), img_pt.y()):
                self.preview.dragging = True
                self.preview.drag_show_box = True
                self.drag_offset = (img_pt.x() - self.text_pos[0], img_pt.y() - self.text_pos[1])
                return True
        return False

    def on_mouse_move(self, event):
        if self.preview.dragging:
            img_pt = self.preview.map_to_img(event.position().toPoint())
            self.text_pos[0] = img_pt.x() - self.drag_offset[0]
            self.text_pos[1] = img_pt.y() - self.drag_offset[1]
            self.clamp_text_within()
            self.recompute()
            return True
        return False

    def on_mouse_release(self, event):
        if event.button() == Qt.LeftButton and self.preview.dragging:
            self.preview.dragging = False
            self.preview.drag_show_box = False
            self.recompute()
            return True
        return False

    def on_text_change(self, *_):
        self.quote = self.quote_input.text()
        self.author = self.author_input.text()
        self.recompute()

    def on_font_change(self, val):
        self.font_size = int(val)
        self.recompute()

    def on_pick_color(self):
        initial = QColor(*self.text_color)
        color = QColorDialog.getColor(initial, self, "Pick Text Color")
        if color.isValid():
            self.text_color = (color.red(), color.green(), color.blue())
            self.recompute()

    def on_style_change(self, style):
        self.current_style = style
        self.recompute()

    def on_load_image(self):
        filt = "Images ({})".format(" ".join(SUPPORTED_EXT))
        path, _ = QFileDialog.getOpenFileName(self, "Load Image", "", filt)
        if path:
            try:
                img = Image.open(path).convert("RGB")
                self.base_image = img
                self.text_pos = [int(self.base_image.width * self.margin_ratio), int(self.base_image.height * self.margin_ratio)]
                self.recompute()
            except Exception as ex:
                QMessageBox.critical(self, "Error", f"Failed to load image:\n{ex}")

    def on_save_image(self):
        if self.result_image is None:
            QMessageBox.warning(self, "No Image", "Nothing to save yet.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Output", "", "PNG (*.png);;JPEG (*.jpg *.jpeg)")
        if not path:
            return
        try:
            ext = os.path.splitext(path)[1].lower()
            img = self.compose_final(shadow_for_preview=False)  # ensure no preview box
            if ext in (".jpg", ".jpeg"):
                img.convert("RGB").save(path, quality=95, subsampling=0, optimize=True)
            else:
                if not ext:
                    path += ".png"
                img.save(path, format="PNG", optimize=True)
        except Exception as ex:
            QMessageBox.critical(self, "Error", f"Failed to save image:\n{ex}")

    def clamp_text_within(self):
        # Keep text block within image bounds with small margin
        img_w, img_h = self.base_image.size
        bbox = self.compute_text_bbox(self.text_pos[0], self.text_pos[1])
        if bbox is None:
            return
        x0, y0, x1, y1 = bbox
        dx = 0
        dy = 0
        if x0 < 0:
            dx = -x0
        if y0 < 0:
            dy = -y0
        if x1 > img_w:
            dx = img_w - x1 if (img_w - x1) < dx else img_w - x1
        if y1 > img_h:
            dy = img_h - y1 if (img_h - y1) < dy else img_h - y1
        self.text_pos[0] += dx
        self.text_pos[1] += dy

    def point_in_text_bbox(self, x, y):
        bbox = self.compute_text_bbox(self.text_pos[0], self.text_pos[1])
        if not bbox:
            return False
        x0, y0, x1, y1 = bbox
        return (x0 <= x <= x1) and (y0 <= y <= y1)

    def pick_style_font(self, size):
        prefs = STYLE_FONT_PREFS.get(self.current_style, STYLE_FONT_PREFS["None"])
        return find_font(prefs, size)

    def compute_text_layout(self, draw, font, max_width):
        quote_lines = wrap_text(self.quote, font, draw, max_width) if self.quote else []
        line_spacing = max(6, int(self.font_size * 0.25))
        q_w, q_h, q_line_heights = measure_multiline(quote_lines, font, draw, line_spacing)

        author_block_lines = []
        if self.author.strip():
            author_text = f"– {self.author.strip()}"
            author_lines = wrap_text(author_text, font, draw, max_width)
            author_block_lines = [""] + author_lines  # blank spacer line
        a_w, a_h, a_line_heights = measure_multiline([ln for ln in author_block_lines if ln != ""], font, draw, line_spacing)
        # total height includes spacer line height if present
        spacer_h = 0
        if author_block_lines:
            spacer_h = int(q_line_heights[-1] * 0.6) if q_line_heights else int(self.font_size * 0.6)
        total_w = max(q_w, a_w)
        total_h = q_h + (spacer_h if author_block_lines else 0) + a_h
        return quote_lines, author_block_lines, (total_w, total_h), line_spacing, spacer_h

    def draw_text_with_shadow(self, img, position, font, color, draw_shadow=False):
        draw = ImageDraw.Draw(img)
        x, y = position
        max_width = int(img.width * (1 - 2 * self.margin_ratio))
        # layout
        quote_lines, author_block_lines, (total_w, total_h), line_spacing, spacer_h = self.compute_text_layout(draw, font, max_width)
        # draw helper
        def draw_lines(lines, start_y):
            yy = start_y
            for ln in lines:
                if ln == "":
                    yy += spacer_h
                    continue
                # shadow
                if draw_shadow:
                    for off in [(-2, 2), (2, 2), (2, -2), (-2, -2)]:
                        draw.text((x + off[0], yy + off[1]), ln, font=font, fill=(0, 0, 0))
                draw.text((x, yy), ln, font=font, fill=color)
                bbox = draw.textbbox((0, 0), ln, font=font)
                lh = bbox[3] - bbox[1]
                yy += lh + line_spacing
            return yy

        # Draw quote and author
        cur_y = y
        cur_y = draw_lines(quote_lines, cur_y)
        if author_block_lines:
            cur_y = draw_lines(author_block_lines, cur_y)
        # return bbox
        return (x, y, x + total_w, y + total_h)

    def compute_text_bbox(self, x, y):
        tmp = self.filtered_bg.copy()
        draw = ImageDraw.Draw(tmp)
        font = self.pick_style_font(self.font_size)
        max_width = int(tmp.width * (1 - 2 * self.margin_ratio))
        quote_lines, author_block_lines, (total_w, total_h), line_spacing, spacer_h = self.compute_text_layout(draw, font, max_width)
        if total_w == 0 or total_h == 0:
            return None
        return (x, y, x + total_w, y + total_h)

    def compose_final(self, shadow_for_preview=True):
        bg = apply_style(self.base_image, self.current_style)
        out = bg.copy()
        font = self.pick_style_font(self.font_size)
        draw = ImageDraw.Draw(out)

        draw_shadow = shadow_for_preview and self.current_style in ("Epic", "Noir")

        bbox = self.draw_text_with_shadow(out, tuple(self.text_pos), font, self.text_color, draw_shadow=draw_shadow)
        # store bbox for preview overlay
        self.preview.set_text_bbox(QRect(bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1]))
        return out

    def update_preview_pixmap(self):
        if self.result_image is None:
            return
        pix = pil_to_qpixmap(self.result_image)
        label_w = max(1, self.preview.width())
        label_h = max(1, self.preview.height())
        img_w = pix.width()
        img_h = pix.height()
        if img_w == 0 or img_h == 0:
            return
        scale = min(label_w / img_w, label_h / img_h)
        disp_w = int(img_w * scale)
        disp_h = int(img_h * scale)
        ox = (label_w - disp_w) // 2
        oy = (label_h - disp_h) // 2
        self.preview.setPixmap(pix.scaled(disp_w, disp_h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.preview.set_viewport_transform(scale, ox, oy)

    def recompute(self):
        try:
            self.filtered_bg = apply_style(self.base_image, self.current_style)
            self.result_image = self.compose_final(shadow_for_preview=True)
            self.update_preview_pixmap()
        except Exception as ex:
            # prevent crashing UI during live edits
            print("Render error:", ex)

def main():
    app = QApplication(sys.argv)
    w = QuoteStudio()
    w.resize(1000, 800)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
