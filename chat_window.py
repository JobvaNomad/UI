# chat_window.py
import html
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QTextBrowser,
    QTextEdit,
    QPushButton,
    QLabel,
    QMessageBox,
    QInputDialog,
)
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
from PyQt6.QtGui import QTextCursor, QKeySequence, QShortcut

import markdown  # pip install markdown

from themes import THEMES          # словарь с темами
from storage import ChatStorage    # класс работы с JSON-чатиками
from backend import get_bot_response  # функция ответа бэка


class ChatInput(QTextEdit):
    """
    Многострочное поле ввода:
    - Enter          → отправка
    - Shift + Enter  → новая строка
    """
    sent = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)

    def keyPressEvent(self, event):
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ):
            # Enter без Shift → отправка
            self.sent.emit()
        else:
            super().keyPressEvent(event)


class ChatWindow(QMainWindow):
    MAX_USER_MESSAGE_CHARS = 10000 # <<< лимит символов для сообщения пользователя

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Нейро-чат RuCortex")
        self.resize(1000, 600)

        self.themes = THEMES
        self.current_theme = "light"
        self.storage = ChatStorage()

        self.chat_history: dict[str, list[dict]] = {}
        self.current_chat: str | None = None

        self.build_ui()

        # --- анимация "Бот думает..." в статусной строке ---
        self.typing_timer = QTimer(self)
        self.typing_timer.setInterval(500)  # смена количества точек каждые 0.5 сек
        self.typing_timer.timeout.connect(self.update_typing_animation)
        self.typing_dot_count = 0
        self.is_bot_typing = False
        # ---------------------------------------------------

        self.apply_theme()
        self.load_chat_list()

        if self.chat_list.count() > 0:
            self.chat_list.setCurrentRow(0)
            self.on_chat_selected(0)
        else:
            self.create_initial_chat()

    # ---------- UI ----------

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # ===== Левая панель (чаты) =====
        left_widget = QWidget()
        left_widget.setObjectName("sidebar")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        header_layout = QHBoxLayout()
        self.chats_label = QLabel("Чаты")
        self.chats_label.setStyleSheet("font-weight: bold;")
        self.connection_label = QLabel("локальный режим")
        header_layout.addWidget(self.chats_label)
        header_layout.addStretch()
        header_layout.addWidget(self.connection_label)
        left_layout.addLayout(header_layout)

        self.chat_list = QListWidget()
        left_layout.addWidget(self.chat_list, 1)

        btns_layout = QHBoxLayout()
        self.new_btn = QPushButton("Новый")
        self.rename_btn = QPushButton("Переимен.")
        self.delete_btn = QPushButton("Удалить")
        btns_layout.addWidget(self.new_btn)
        btns_layout.addWidget(self.rename_btn)
        btns_layout.addWidget(self.delete_btn)
        left_layout.addLayout(btns_layout)

        self.theme_btn = QPushButton("☀ Светлая тема")
        left_layout.addWidget(self.theme_btn)

        # фиксируем ширину списка чатов
        left_widget.setFixedWidth(250)
        root_layout.addWidget(left_widget)

        # ===== Правая панель (чат) =====
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        top_layout = QHBoxLayout()
        self.logo_label = QLabel("RuCortex")
        self.logo_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.subtitle_label = QLabel("AI-поиск для бизнеса")
        self.subtitle_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        self.current_chat_label = QLabel("")

        top_layout.addWidget(self.logo_label)
        top_layout.addSpacing(12)
        top_layout.addWidget(self.subtitle_label)
        top_layout.addSpacing(12)
        top_layout.addWidget(self.current_chat_label)
        top_layout.addStretch()
        right_layout.addLayout(top_layout)

        self.chat_view = QTextBrowser()
        self.chat_view.setOpenLinks(False)
        self.chat_view.setOpenExternalLinks(False)
        self.chat_view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        right_layout.addWidget(self.chat_view, 1)

        # строка статуса — именно здесь будет "Бот думает..."
        self.typing_label = QLabel("")
        self.typing_label.setStyleSheet("color: #6B7280; font-size: 9pt;")
        right_layout.addWidget(self.typing_label)

        bottom_layout = QHBoxLayout()
        self.input_line = ChatInput()
        self.input_line.setPlaceholderText("Напишите сообщение...")
        self.input_line.setFixedHeight(80)  # побольше, чтобы влезал длинный промпт
        self.send_btn = QPushButton("Отправить")
        self.send_btn.setObjectName("sendButton")
        self.send_btn.setEnabled(False)
        bottom_layout.addWidget(self.input_line, 1)
        bottom_layout.addWidget(self.send_btn)
        right_layout.addLayout(bottom_layout)

        root_layout.addWidget(right_widget, 1)

        # Сигналы
        self.chat_list.currentRowChanged.connect(self.on_chat_selected)
        self.new_btn.clicked.connect(self.new_chat)
        self.rename_btn.clicked.connect(self.rename_chat)
        self.delete_btn.clicked.connect(self.delete_chat)
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.send_btn.clicked.connect(self.send_message)
        self.input_line.sent.connect(self.send_message)        # Enter
        self.input_line.textChanged.connect(self.on_input_changed)
        self.chat_view.anchorClicked.connect(self.on_anchor_clicked)

        # Горячие клавиши
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_chat)
        QShortcut(QKeySequence("F2"), self, activated=self.rename_chat)
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_chat)

    # ---------- ТЕМА ----------

    def apply_theme(self):
        t = self.themes[self.current_theme]

        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {t["bg"]};
                color: {t["fg"]};
                font-family: "Segoe UI", sans-serif;
                font-size: 10pt;
            }}
            QListWidget {{
                background-color: {t["list_bg"]};
                border: 1px solid {t["border"]};
            }}
            QListWidget::item:selected {{
                background-color: {t["list_sel_bg"]};
                color: {t["list_sel_fg"]};
            }}
            QPushButton {{
                background-color: {t["bg_button"]};
                color: {t["fg"]};
                border-radius: 4px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                background-color: {t["bg_button_active"]};
            }}
            QPushButton#sendButton {{
                background-color: {t["accent"]};
                color: #ffffff;
            }}
            QPushButton#sendButton:hover {{
                background-color: {t["accent_dark"]};
            }}
            QTextBrowser {{
                background-color: {t["bg_chat"]};
                border: 1px solid {t["border"]};
            }}
            QTextEdit {{
                background-color: {t["bg_chat"]};
                border: 1px solid {t["border"]};
                padding: 4px;
            }}
        """
        )

        sidebar = self.findChild(QWidget, "sidebar")
        if sidebar is not None:
            sidebar.setStyleSheet(f"background-color: {t['bg_sidebar']};")

        self.connection_label.setStyleSheet(f"color: {t['fg_muted']};")
        self.logo_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #7DD3FC;"
        )
        self.subtitle_label.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #A855F7;"
        )
        self.current_chat_label.setStyleSheet(
            f"font-size: 11px; color: {t['fg_muted']};"
        )

        self.theme_btn.setText(
            "☀ Светлая тема" if self.current_theme == "dark" else "🌙 Тёмная тема"
        )

        if self.current_chat:
            history = self.chat_history.get(self.current_chat, [])
            self.render_history(history)

    def toggle_theme(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.apply_theme()

    # ---------- ЗАГРУЗКА / СОХРАНЕНИЕ ЧАТОВ ----------

    def load_chat_list(self):
        self.chat_list.clear()
        self.chat_history.clear()

        for name in self.storage.list_chat_names():
            self.chat_list.addItem(name)
            self.chat_history[name] = self.storage.load_chat(name)

    def save_chat(self, name: str):
        self.storage.save_chat(name, self.chat_history.get(name, []))

    def generate_default_chat_name(self) -> str:
        i = 1
        while True:
            name = f"Чат {i}"
            if name not in self.chat_history and not self.storage.chat_exists(name):
                return name
            i += 1

    def create_initial_chat(self):
        name = self.generate_default_chat_name()
        self.chat_history[name] = []
        self.save_chat(name)
        self.load_chat_list()
        items = self.chat_list.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self.chat_list.setCurrentItem(items[0])
            row = self.chat_list.row(items[0])
            self.on_chat_selected(row)

    # ---------- ОПЕРАЦИИ С ЧАТАМИ ----------

    def new_chat(self):
        name, ok = QInputDialog.getText(self, "Новый чат", "Название чата:")
        if not ok:
            return
        name = name.strip()
        if not name:
            name = self.generate_default_chat_name()

        if name in self.chat_history or self.storage.chat_exists(name):
            QMessageBox.critical(self, "Ошибка", "Чат с таким именем уже существует.")
            return

        self.chat_history[name] = []
        self.save_chat(name)
        self.load_chat_list()
        items = self.chat_list.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self.chat_list.setCurrentItem(items[0])
            row = self.chat_list.row(items[0])
            self.on_chat_selected(row)

    def rename_chat(self):
        item = self.chat_list.currentItem()
        if not item:
            return
        old_name = item.text()

        new_name, ok = QInputDialog.getText(
            self, "Переименовать чат", "Новое название:", text=old_name
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return

        if new_name in self.chat_history or self.storage.chat_exists(new_name):
            QMessageBox.critical(self, "Ошибка", "Чат с таким именем уже существует.")
            return

        self.storage.rename_chat(old_name, new_name)

        self.chat_history[new_name] = self.chat_history.pop(old_name, [])
        if self.current_chat == old_name:
            self.current_chat = new_name

        self.save_chat(new_name)
        self.load_chat_list()
        items = self.chat_list.findItems(new_name, Qt.MatchFlag.MatchExactly)
        if items:
            self.chat_list.setCurrentItem(items[0])
            row = self.chat_list.row(items[0])
            self.on_chat_selected(row)

    def delete_chat(self):
        item = self.chat_list.currentItem()
        if not item:
            return
        name = item.text()

        reply = QMessageBox.question(
            self,
            "Удалить чат",
            f"Удалить чат «{name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.chat_history.pop(name, None)
        self.storage.delete_chat(name)

        self.load_chat_list()
        if self.chat_list.count() > 0:
            self.chat_list.setCurrentRow(0)
            self.on_chat_selected(0)
        else:
            self.current_chat = None
            self.current_chat_label.setText("")
            self.chat_view.clear()
            self.chat_view.setHtml("<p>Нет чатов. Создайте новый слева.</p>")

    # ---------- ОТОБРАЖЕНИЕ И ИСТОРИЯ ----------

    def on_chat_selected(self, row: int):
        if row < 0:
            return
        item = self.chat_list.item(row)
        if not item:
            return
        name = item.text()
        self.current_chat = name
        self.current_chat_label.setText(f"Чат: {name}")
        self.stop_typing_animation()  # при переключении чата убираем "думаю..."
        history = self.chat_history.get(name, [])
        self.render_history(history)

    def render_history(self, history: list[dict]):
        self.chat_view.clear()
        if not history:
            self.chat_view.setHtml(
                "<p style='color:#6B7280;'>Начните диалог — напишите сообщение внизу.</p>"
            )
            return

        for idx, m in enumerate(history):
            sender = m.get("sender", "bot")
            text = m.get("text", "")
            time = m.get("time", "")
            date = m.get("date", "")
            rating = m.get("rating", "")
            self.append_message_to_view(sender, text, time, date, rating, idx)

    def format_message_html(
        self,
        sender: str,
        text: str,
        time: str = "",
        date: str = "",
        rating: str = "",
        index: int | None = None,
    ) -> str:
        t = self.themes[self.current_theme]

        # подпись "16:23 · 27.11.2025"
        meta_parts = []
        if time:
            meta_parts.append(time)
        if date:
            meta_parts.append(date)
        meta = " · ".join(meta_parts)

        # ----- пользователь (справа) -----
        if sender == "user":
            esc = html.escape(text).replace("\n", "<br>")
            footer = (
                f"<div style='font-size:8pt; color:{t['fg_muted']}; "
                f"text-align:right; margin-top:4px;'>{meta}</div>"
                if meta
                else ""
            )
            right_cell = f"""
            <div style="
                display:inline-block;
                background-color:{t['bubble_user']};
                padding:8px 12px;
                border-radius:12px;
                max-width:70%;
                color:{t['fg']};
                font-family:'Segoe UI',sans-serif;
                font-size:10pt;
                text-align:left;
            ">
              <b>Вы:</b><br>{esc}{footer}
            </div>
            """

            return f"""
<table width="100%" cellspacing="0" cellpadding="0"
       style="margin-top:10px; margin-bottom:10px;">
  <tr>
    <td width="50%" valign="top" style="padding:4px 6px;"></td>
    <td width="50%" valign="top" align="right" style="padding:4px 6px;">{right_cell}</td>
  </tr>
</table>
"""

        # ----- бот (по центру, с Markdown) -----
        if index is None:
            index = -1

        # рендерим Markdown → HTML
        bot_html = markdown.markdown(
            text,
            extensions=["fenced_code", "tables", "nl2br"],
        )

        meta_div = (
            f"<div style='font-size:8pt; color:{t['fg_muted']}; "
            f"text-align:right; margin-top:8px;'>{meta}</div>"
            if meta
            else ""
        )

        # лайк / дизлайк
        like_selected = rating == "like"
        dislike_selected = rating == "dislike"

        dim_color = "#D1D5DB"

        if like_selected:
            like_color = t["accent"]
            dislike_color = dim_color
        elif dislike_selected:
            like_color = dim_color
            dislike_color = t["accent"]
        else:
            like_color = t["fg_muted"]
            dislike_color = t["fg_muted"]

        like_bg = "#E0E7FF" if like_selected else "transparent"
        dislike_bg = "#FEE2E2" if dislike_selected else "transparent"

        like_border = t["accent"] if like_selected else "#E5E7EB"
        dislike_border = t["accent"] if dislike_selected else "#E5E7EB"

        rating_div = ""
        if index >= 0:
            rating_div = f"""
<div style="font-size:9pt; text-align:right; margin-top:4px;">
  <a href="rate:{index}:like"
     style="text-decoration:none;
            color:{like_color};
            background-color:{like_bg};
            padding:4px 12px;
            border-radius:999px;
            border:1px solid {like_border};
            margin-right:10px;
            display:inline-block;">
    <span style="font-size:15pt; vertical-align:middle;">👍</span>
    <span style="margin-left:4px; vertical-align:middle;">Полезно</span>
  </a>
  <a href="rate:{index}:dislike"
     style="text-decoration:none;
            color:{dislike_color};
            background-color:{dislike_bg};
            padding:4px 12px;
            border-radius:999px;
            border:1px solid {dislike_border};
            display:inline-block;">
    <span style="font-size:15pt; vertical-align:middle;">👎</span>
    <span style="margin-left:4px; vertical-align:middle;">Не помогает</span>
  </a>
</div>
"""

        bubble_html = f"""
<div style="
    display:inline-block;
    background-color:{t['bubble_bot']};
    padding:12px 16px;
    border-radius:16px;
    max-width:80%;
    color:{t['fg']};
    font-family:'Segoe UI',sans-serif;
    font-size:10pt;
    text-align:left;
">
  <div style="font-weight:bold; margin-bottom:4px;">Бот:</div>
  {bot_html}
  {meta_div}
  {rating_div}
</div>
"""
        return f"""
<table width="100%" cellspacing="0" cellpadding="0"
       style="margin-top:10px; margin-bottom:10px;">
  <tr>
    <td valign="top" align="center" style="padding:4px 6px;">{bubble_html}</td>
  </tr>
</table>
"""

    def append_message_to_view(
            self,
            sender: str,
            text: str,
            time: str = "",
            date: str = "",
            rating: str = "",
            index: int | None = None,
    ):
        # --- запоминаем положение скролла до вставки ---
        scrollbar = self.chat_view.verticalScrollBar()
        old_value = scrollbar.value()
        # считаем, что "внизу", если ползунок почти у максимума
        was_at_bottom = old_value >= scrollbar.maximum() - 2

        html_snippet = self.format_message_html(
            sender, text, time, date, rating, index
        )

        cursor = self.chat_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html_snippet)
        cursor.insertBlock()
        self.chat_view.setTextCursor(cursor)

        # ВАЖНО: НЕ вызываем ensureCursorVisible(), он всегда тянет вниз

        # --- восстанавливаем позицию скролла ---
        if was_at_bottom:
            # если пользователь был внизу — оставляем автоскролл
            scrollbar.setValue(scrollbar.maximum())
        else:
            # если листал историю — возвращаем туда, где он был
            scrollbar.setValue(old_value)

    # ---------- АНИМАЦИЯ "Бот думает..." ----------

    def start_typing_animation(self):
        self.is_bot_typing = True
        self.typing_dot_count = 0
        self.typing_timer.start()

    def stop_typing_animation(self):
        self.is_bot_typing = False
        self.typing_timer.stop()
        self.typing_label.setText("")

    def update_typing_animation(self):
        if not self.is_bot_typing:
            return
        self.typing_dot_count = (self.typing_dot_count + 1) % 4  # 0..3
        dots = "." * self.typing_dot_count
        self.typing_label.setText(f"Бот думает{dots}")

    # ---------- ВСПОМОГАТЕЛЬНОЕ ----------

    def on_input_changed(self):
        text = self.input_line.toPlainText()

        # <<< ограничиваем длину текста
        if len(text) > self.MAX_USER_MESSAGE_CHARS:
            text = text[:self.MAX_USER_MESSAGE_CHARS]

            self.input_line.blockSignals(True)
            self.input_line.setPlainText(text)
            cursor = self.input_line.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.input_line.setTextCursor(cursor)
            self.input_line.blockSignals(False)
        # <<<

        self.send_btn.setEnabled(bool(text.strip()))

    def on_anchor_clicked(self, url: QUrl):
        full = url.toString()
        if not full.startswith("rate:"):
            return

        try:
            _, idx_str, action = full.split(":", 2)
            idx = int(idx_str)
        except ValueError:
            return

        if action not in ("like", "dislike"):
            return
        if not self.current_chat:
            return

        history = self.chat_history.get(self.current_chat, [])
        if not (0 <= idx < len(history)):
            return

        msg = history[idx]
        if msg.get("sender") != "bot":
            return

        msg["rating"] = action
        self.save_chat(self.current_chat)
        self.render_history(history)

    # ---------- ВЫЗОВ БЭКЕНДА ----------

    def call_backend(self, user_text: str) -> str:
        return get_bot_response(user_text)

    # ---------- ОТПРАВКА СООБЩЕНИЯ ----------

    def send_message(self):
        if not self.current_chat:
            return

        raw_text = self.input_line.toPlainText()

        # <<< проверяем лимит перед отправкой
        if len(raw_text) > self.MAX_USER_MESSAGE_CHARS:
            QMessageBox.warning(
                self,
                "Слишком длинное сообщение",
                f"Максимум {self.MAX_USER_MESSAGE_CHARS} символов.\n"
                f"Сейчас: {len(raw_text)}",
            )
            return
        # <<<

        text = raw_text.strip()
        if not text:
            return

        if not self.chat_history.get(self.current_chat):
            self.chat_view.clear()

        self.input_line.clear()
        self.on_input_changed()

        now = datetime.now()
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%d.%m.%Y")

        history = self.chat_history.setdefault(self.current_chat, [])

        # пользователь
        history.append(
            {
                "sender": "user",
                "text": text,
                "time": time_str,
                "date": date_str,
            }
        )
        user_index = len(history) - 1
        self.append_message_to_view("user", text, time_str, date_str, "", user_index)
        self.save_chat(self.current_chat)

        # запускаем анимацию "Бот думает..."
        self.start_typing_animation()

        chat_name = self.current_chat
        user_text_for_reply = text

        # пока нет реального бэка — просто таймер;
        QTimer.singleShot(
            1500,
            lambda cn=chat_name, ut=user_text_for_reply: self.produce_bot_reply(cn, ut),
        )

    def produce_bot_reply(self, chat_name: str, user_text: str):
        # здесь можно будет заменить на реальный долгий вызов
        bot_text = self.call_backend(user_text)

        self.stop_typing_animation()

        now_bot = datetime.now()
        bot_time_str = now_bot.strftime("%H:%M")
        bot_date_str = now_bot.strftime("%d.%m.%Y")

        history = self.chat_history.setdefault(chat_name, [])
        history.append(
            {
                "sender": "bot",
                "text": bot_text,
                "time": bot_time_str,
                "date": bot_date_str,
                "rating": "",
            }
        )
        bot_index = len(history) - 1

        if chat_name == self.current_chat:
            self.append_message_to_view(
                "bot", bot_text, bot_time_str, bot_date_str, "", bot_index
            )

        self.save_chat(chat_name)
