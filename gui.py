import math
import platform
import queue
import random
import shutil
import threading
import time
from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QTimer, Qt, Signal, QObject
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from brain import ask_ai, decide_actions
from commands import run_action
from voice import listen, speak, stop_speaking


CYAN = "#38d5ff"
BLUE = "#4f7cff"
GOLD = "#ffc857"
GREEN = "#3ee98f"
RED = "#ff5f78"
PURPLE = "#b477ff"
TEXT = "#e8f1ff"
MUTED = "#8aa0bd"
PANEL = "rgba(14, 24, 38, 165)"
CHAT_ACKS = [
    "Yeah, one sec.",
    "Got you.",
    "Okay, let me think.",
    "Hmm, good question.",
    "Alright, I got you.",
]
SLOW_CHAT_ACKS = [
    "Still thinking.",
    "Almost there.",
    "Give me a second.",
]


class EventBus(QObject):
    state = Signal(str)
    command = Signal(str)
    result = Signal(str)
    actions = Signal(list)
    memory = Signal(str)
    notification = Signal(str)
    stopped = Signal()


class GlassPanel(QFrame):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setStyleSheet(
            """
            QFrame#GlassPanel {
                background: rgba(12, 22, 35, 178);
                border: 1px solid rgba(56, 213, 255, 88);
                border-radius: 18px;
            }
            QLabel {
                background: transparent;
            }
            """
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setColor(QColor(56, 213, 255, 45))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 16, 18, 16)
        self.layout.setSpacing(10)

        if title:
            label = QLabel(title.upper())
            label.setStyleSheet(f"color: {CYAN}; letter-spacing: 2px;")
            label.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.layout.addWidget(label)


class OrbWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "idle"
        self.phase = 0.0
        self.setMinimumSize(520, 430)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def set_state(self, state):
        self.state = state
        self.update()

    def tick(self):
        self.phase += 0.035
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, QColor(4, 8, 16, 35))
        cx = rect.width() / 2
        cy = rect.height() / 2

        color = {
            "idle": QColor(CYAN),
            "listening": QColor(CYAN),
            "thinking": QColor(GOLD),
            "speaking": QColor(GREEN),
            "warning": QColor(RED),
        }.get(self.state, QColor(CYAN))

        self.draw_grid(painter)
        self.draw_radar(painter, cx, cy, color)

        activity = {
            "idle": 0.35,
            "listening": 1.0,
            "thinking": 0.75,
            "speaking": 0.92,
        }.get(self.state, 0.4)

        for i in range(5):
            radius = 58 + i * 34 + math.sin(self.phase * (1.2 + i * 0.15)) * 11 * activity
            alpha = max(45, 190 - i * 34)
            pen = QPen(QColor(color.red(), color.green(), color.blue(), alpha), max(1, 5 - i))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

        for i in range(6):
            start = int((self.phase * 900 + i * 960) % 5760)
            span = 380 + i * 58
            radius = 112 + i * 15
            pen = QPen(QColor(color.red(), color.green(), color.blue(), 180 if i % 2 == 0 else 95), 3)
            painter.setPen(pen)
            painter.drawArc(QRect(int(cx - radius), int(cy - radius), radius * 2, radius * 2), start, span)

        glow = QLinearGradient(cx - 70, cy - 70, cx + 70, cy + 70)
        glow.setColorAt(0.0, QColor(56, 213, 255, 210))
        glow.setColorAt(0.5, QColor(79, 124, 255, 160))
        glow.setColorAt(1.0, QColor(180, 119, 255, 120))
        core = 50 + math.sin(self.phase * 2.8) * 7 * activity
        painter.setPen(QPen(color, 3))
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), core, core)

        painter.setPen(QPen(QColor(232, 241, 255, 235)))
        painter.setFont(QFont("Segoe UI", 16, QFont.Bold))
        painter.drawText(QRect(0, int(cy + 132), rect.width(), 40), Qt.AlignCenter, self.state.upper())
        painter.setPen(QColor(MUTED))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QRect(0, int(cy + 165), rect.width(), 26), Qt.AlignCenter, "Voice lock engaged after 2 seconds of silence")

    def draw_grid(self, painter):
        painter.setPen(QPen(QColor(38, 70, 102, 42), 1))
        for x in range(0, self.width(), 42):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 42):
            painter.drawLine(0, y, self.width(), y)

        scan_y = int((self.phase * 70) % max(self.height(), 1))
        painter.setPen(QPen(QColor(56, 213, 255, 58), 2))
        painter.drawLine(0, scan_y, self.width(), scan_y)

    def draw_radar(self, painter, cx, cy, color):
        for i in range(72):
            angle = math.pi * 2 * i / 72
            outer = 218
            inner = 200 if i % 6 else 184
            alpha = 155 if i % 6 == 0 else 72
            painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), alpha), 2 if i % 6 == 0 else 1))
            painter.drawLine(
                QPointF(cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
                QPointF(cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
            )


class GraphWidget(QWidget):
    def __init__(self, title, color, parent=None):
        super().__init__(parent)
        self.title = title
        self.color = QColor(color)
        self.values = [random.randint(25, 65) for _ in range(42)]
        self.setMinimumHeight(92)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.add_value)
        self.timer.start(900)

    def add_value(self):
        last = self.values[-1]
        value = max(3, min(98, last + random.randint(-13, 14)))
        self.values = self.values[1:] + [value]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(4, 6, -4, -6)

        painter.setPen(QColor(MUTED))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(rect, Qt.AlignTop | Qt.AlignLeft, self.title.upper())
        painter.setPen(QColor(TEXT))
        painter.drawText(rect, Qt.AlignTop | Qt.AlignRight, f"{self.values[-1]}%")

        graph = rect.adjusted(0, 26, 0, 0)
        path = QPainterPath()
        for i, value in enumerate(self.values):
            x = graph.left() + graph.width() * i / (len(self.values) - 1)
            y = graph.bottom() - graph.height() * value / 100
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        painter.setPen(QPen(QColor(self.color.red(), self.color.green(), self.color.blue(), 210), 2))
        painter.drawPath(path)
        painter.setBrush(QColor(self.color.red(), self.color.green(), self.color.blue(), 210))
        painter.setPen(Qt.NoPen)
        last_x = graph.right()
        last_y = graph.bottom() - graph.height() * self.values[-1] / 100
        painter.drawEllipse(QPointF(last_x, last_y), 4, 4)


class CommandChip(QFrame):
    def __init__(self, action, value):
        super().__init__()
        self.setStyleSheet(
            f"""
            QFrame {{
                background: rgba(20, 34, 54, 190);
                border: 1px solid rgba(56, 213, 255, 85);
                border-radius: 13px;
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        title = QLabel(action.replace("_", " ").title())
        title.setStyleSheet(f"color: {CYAN};")
        title.setFont(QFont("Segoe UI", 10, QFont.Bold))
        body = QLabel(value or "Ready")
        body.setStyleSheet(f"color: {TEXT};")
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(body)


class JarvisGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IMOT HUD")
        self.setMinimumSize(1120, 720)
        self.resize(1240, 760)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.bus = EventBus()
        self.running = False
        self.worker = None
        self.drag_position = None
        self.memory = []
        self.command_lock = threading.Lock()
        self.notice_queue = queue.Queue()

        self.build_ui()
        self.connect_signals()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.update_clock()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet(
            """
            QWidget {
                color: #e8f1ff;
                font-family: Segoe UI;
            }
            """
        )

        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)

        self.shell = QFrame()
        self.shell.setObjectName("Shell")
        self.shell.setStyleSheet(
            """
            QFrame#Shell {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(4, 8, 16, 232),
                    stop:0.45 rgba(8, 15, 30, 224),
                    stop:1 rgba(24, 12, 42, 218));
                border: 1px solid rgba(56, 213, 255, 95);
                border-radius: 24px;
            }
            """
        )
        outer.addWidget(self.shell)

        layout = QVBoxLayout(self.shell)
        layout.setContentsMargins(24, 18, 24, 24)
        layout.setSpacing(18)

        layout.addLayout(self.build_top_bar())

        body = QHBoxLayout()
        body.setSpacing(18)
        layout.addLayout(body, 1)

        body.addWidget(self.build_left_bar())

        center = QVBoxLayout()
        center.setSpacing(16)
        body.addLayout(center, 1)

        orb_panel = GlassPanel()
        orb_panel.layout.setContentsMargins(8, 8, 8, 8)
        self.orb = OrbWidget()
        orb_panel.layout.addWidget(self.orb)
        center.addWidget(orb_panel, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        center.addLayout(bottom)
        self.command_label = self.info_panel("COMMAND", "Waiting for voice input")
        self.result_label = self.info_panel("RESPONSE", "Ready")
        bottom.addWidget(self.command_label["panel"])
        bottom.addWidget(self.result_label["panel"])

        body.addWidget(self.build_right_stack())
        layout.addLayout(self.build_command_bar())

        self.notification = QLabel("")
        self.notification.setParent(self.shell)
        self.notification.setStyleSheet(
            f"""
            background: rgba(10, 24, 38, 230);
            color: {TEXT};
            border: 1px solid rgba(255, 200, 87, 150);
            border-radius: 14px;
            padding: 12px 16px;
            """
        )
        self.notification.hide()

    def build_top_bar(self):
        top = QHBoxLayout()
        title = QLabel("IMOT")
        title.setStyleSheet(f"color: {CYAN}; letter-spacing: 5px;")
        title.setFont(QFont("Segoe UI", 25, QFont.Bold))
        top.addWidget(title)

        scan = QLabel("SYSTEM READY")
        scan.setStyleSheet(f"color: {GOLD};")
        scan.setFont(QFont("Consolas", 10, QFont.Bold))
        top.addWidget(scan)
        top.addStretch()

        self.status_dot = QLabel("ONLINE")
        self.status_dot.setStyleSheet(f"color: {GREEN};")
        self.status_dot.setFont(QFont("Segoe UI", 10, QFont.Bold))
        top.addWidget(self.status_dot)

        self.clock = QLabel("")
        self.clock.setStyleSheet(f"color: {TEXT};")
        self.clock.setFont(QFont("Consolas", 12, QFont.Bold))
        top.addWidget(self.clock)

        close = QPushButton("X")
        close.setFixedSize(34, 34)
        close.setStyleSheet(
            f"QPushButton {{ background: rgba(255,95,120,55); color: {TEXT}; border-radius: 17px; font-size: 18px; }}"
            f"QPushButton:hover {{ background: {RED}; }}"
        )
        close.clicked.connect(self.close)
        top.addWidget(close)
        return top

    def build_left_bar(self):
        panel = GlassPanel("Controls")
        panel.setFixedWidth(150)
        self.toggle_button = QPushButton("START")
        self.toggle_button.clicked.connect(self.toggle_listening)
        self.toggle_button.setStyleSheet(self.button_style(BLUE))
        panel.layout.addWidget(self.toggle_button)

        panel.layout.addStretch()
        return panel

    def build_right_stack(self):
        stack = QVBoxLayout()
        stack.setSpacing(16)

        system = GlassPanel("System Monitor")
        system.layout.addWidget(GraphWidget("CPU Signal", CYAN))
        system.layout.addWidget(GraphWidget("Memory Flow", PURPLE))
        disk = shutil.disk_usage(".")
        disk_value = int(disk.used / disk.total * 100)
        disk_label = QLabel(f"Storage matrix: {disk_value}% used")
        disk_label.setStyleSheet(f"color: {TEXT};")
        system.layout.addWidget(disk_label)
        stack.addWidget(system)

        actions = GlassPanel("Action Queue")
        self.actions_area = QVBoxLayout()
        self.actions_area.setSpacing(8)
        actions.layout.addLayout(self.actions_area)
        self.set_actions([])
        stack.addWidget(actions, 1)

        memory = GlassPanel("Memory Core")
        self.memory_label = QLabel("No recent context")
        self.memory_label.setWordWrap(True)
        self.memory_label.setStyleSheet(f"color: {MUTED};")
        memory.layout.addWidget(self.memory_label)
        stack.addWidget(memory)

        holder = QWidget()
        holder.setFixedWidth(340)
        holder.setLayout(stack)
        return holder

    def build_command_bar(self):
        bar = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type or speak a command, then press Enter...")
        self.input.returnPressed.connect(self.run_typed_command)
        self.input.setStyleSheet(
            f"""
            QLineEdit {{
                background: rgba(7, 16, 28, 200);
                border: 1px solid rgba(56, 213, 255, 110);
                border-radius: 18px;
                padding: 14px 18px;
                color: {TEXT};
                selection-background-color: {BLUE};
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid rgba(255, 200, 87, 190);
            }}
            """
        )
        bar.addWidget(self.input, 1)
        return bar

    def info_panel(self, title, value):
        panel = GlassPanel(title)
        panel.setMinimumHeight(118)
        label = QLabel(value)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {TEXT}; font-size: 13px;")
        panel.layout.addWidget(label)
        return {"panel": panel, "label": label}

    def button_style(self, color):
        return (
            f"QPushButton {{ background: {color}; color: {TEXT}; border: 1px solid rgba(56,213,255,105); "
            "border-radius: 14px; padding: 12px; font-weight: 700; }}"
            f"QPushButton:hover {{ border: 1px solid {GOLD}; background: rgba(56,213,255,90); }}"
        )

    def connect_signals(self):
        self.bus.state.connect(self.set_state)
        self.bus.command.connect(self.set_command)
        self.bus.result.connect(self.set_result)
        self.bus.actions.connect(self.set_actions)
        self.bus.memory.connect(self.set_memory)
        self.bus.notification.connect(self.show_notification)
        self.bus.stopped.connect(self.mark_stopped)

    def toggle_listening(self):
        if self.running:
            self.running = False
            self.mark_stopped()
            return

        self.running = True
        self.toggle_button.setText("STOP")
        self.toggle_button.setStyleSheet(self.button_style(GREEN))
        self.worker = threading.Thread(target=self.assistant_loop, daemon=True)
        self.worker.start()

    def assistant_loop(self):
        self.bus.state.emit("speaking")
        speak("Hi, I'm IMOT")
        while self.running:
            self.bus.state.emit("listening")
            command = listen()
            if not self.running:
                break
            if command:
                self.process_command(command)
        self.bus.stopped.emit()

    def run_typed_command(self):
        command = self.input.text().strip()
        if not command:
            return
        self.input.clear()
        threading.Thread(target=self.process_command, args=(command,), daemon=True).start()

    def process_command(self, command):
        self.bus.command.emit(command)
        clean_command = command.lower().strip()
        if clean_command == "stop":
            stop_speaking()
            self.bus.result.emit("Stopped speaking")
            if self.running:
                self.bus.state.emit("listening")
            else:
                self.bus.state.emit("idle")
            return

        if clean_command in {"goodbye", "bye", "exit assistant", "quit assistant", "shutdown assistant"}:
            self.bus.state.emit("speaking")
            speak("Goodbye")
            self.running = False
            self.bus.stopped.emit()
            return

        with self.command_lock:
            self.bus.state.emit("thinking")
            plans = decide_actions(command)
            self.bus.actions.emit(plans)
            spoken_results = []

            for plan in plans:
                action = plan.get("action")
                value = plan.get("value")
                if action == "chat" and not value:
                    thinking_message = random.choice(CHAT_ACKS)
                    self.bus.result.emit(thinking_message)
                    self.bus.state.emit("speaking")
                    speak(thinking_message)
                    self.bus.state.emit("thinking")
                    value = self.ask_ai_with_updates(command)

                result = run_action(action, value) or "I did not understand that command"
                spoken_results.append(result)
                self.bus.result.emit(result)
                self.bus.state.emit("speaking")
                speak(result)

            self.remember(command, " ".join(spoken_results), plans)
            self.bus.memory.emit(self.memory_preview())
            self.bus.notification.emit("Memory core updated")
            if self.running:
                self.bus.state.emit("listening")
            else:
                self.bus.state.emit("idle")

    def ask_ai_with_updates(self, command):
        responses = queue.Queue(maxsize=1)

        def think():
            try:
                responses.put(ask_ai(command, self.memory_context()))
            except Exception as error:
                responses.put(f"I'm having trouble thinking that through right now: {error}")

        thinker = threading.Thread(target=think, daemon=True)
        thinker.start()
        next_update = time.monotonic() + 2.4
        update_index = 0

        while True:
            try:
                return responses.get(timeout=0.2)
            except queue.Empty:
                if not thinker.is_alive():
                    return "I lost that thought for a second. Try asking me again."

                if time.monotonic() >= next_update and update_index < len(SLOW_CHAT_ACKS):
                    message = SLOW_CHAT_ACKS[update_index]
                    update_index += 1
                    self.bus.result.emit(message)
                    self.bus.state.emit("speaking")
                    speak(message)
                    self.bus.state.emit("thinking")
                    next_update = time.monotonic() + 4.0

    def set_state(self, state):
        self.orb.set_state(state)
        self.status_dot.setText(state.upper())
        self.status_dot.setStyleSheet(f"color: {GREEN if state != 'warning' else RED};")

    def set_command(self, command):
        self.command_label["label"].setText(command)
        self.pop_widget(self.command_label["panel"])

    def set_result(self, result):
        self.result_label["label"].setText(result)
        self.pop_widget(self.result_label["panel"])

    def set_memory(self, text):
        self.memory_label.setText(text)

    def set_actions(self, actions):
        while self.actions_area.count():
            item = self.actions_area.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not actions:
            label = QLabel("No active tasks")
            label.setStyleSheet(f"color: {MUTED};")
            self.actions_area.addWidget(label)
            return

        for plan in actions:
            chip = CommandChip(plan.get("action", "unknown"), plan.get("value") or "Ready")
            self.actions_area.addWidget(chip)

        self.actions_area.addStretch()

    def show_notification(self, text):
        self.notification.setText(text)
        self.notification.adjustSize()
        start = QRect(self.shell.width(), 26, self.notification.width(), self.notification.height())
        end = QRect(self.shell.width() - self.notification.width() - 26, 26, self.notification.width(), self.notification.height())
        self.notification.setGeometry(start)
        self.notification.show()
        animation = QPropertyAnimation(self.notification, b"geometry", self)
        animation.setDuration(420)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.OutBack)
        animation.start()
        self.notification_animation = animation
        QTimer.singleShot(4200, self.notification.hide)

    def pop_widget(self, widget):
        geometry = widget.geometry()
        expanded = geometry.adjusted(-4, -4, 4, 4)
        animation = QPropertyAnimation(widget, b"geometry", self)
        animation.setDuration(220)
        animation.setKeyValueAt(0.0, geometry)
        animation.setKeyValueAt(0.45, expanded)
        animation.setKeyValueAt(1.0, geometry)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
        self.pop_animation = animation

    def mark_stopped(self):
        self.running = False
        self.toggle_button.setText("START")
        self.toggle_button.setStyleSheet(self.button_style(BLUE))
        self.set_state("idle")

    def update_clock(self):
        self.clock.setText(datetime.now().strftime("%H:%M:%S  |  %A, %d %b"))

    def remember(self, command, response, plans):
        self.memory.append({"command": command, "response": response, "plans": plans})
        self.memory = self.memory[-8:]

    def memory_context(self):
        lines = []
        for item in self.memory[-4:]:
            lines.append(f"User asked: {item['command']}")
            lines.append(f"Assistant answered: {item['response']}")
        return "\n".join(lines)

    def memory_preview(self):
        if not self.memory:
            return "No recent context"
        last = self.memory[-1]
        response = last["response"]
        if len(response) > 180:
            response = response[:177] + "..."
        return f"Last command: {last['command']}\nLast response: {response}\nHost: {platform.node()}"

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_position and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None

    def run(self):
        self.show()


def launch_gui():
    app = QApplication([])
    window = JarvisGUI()
    window.run()
    app.exec()


if __name__ == "__main__":
    launch_gui()
