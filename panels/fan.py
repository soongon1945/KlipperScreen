import logging
import re

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel

CHANGEABLE_FANS = ["fan", "fan_generic"]


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        title = title or _("Fan")
        super().__init__(screen, title)
        self.fan_speed = {}
        self.devices = {}
        # Create a grid for all devices
        self.labels["devices"] = Gtk.Grid(valign=Gtk.Align.CENTER)

        self.load_fans()

        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.labels["devices"])

        self.content.add(scroll)

    def process_update(self, action, data):
        if action != "notify_status_update":
            return

        for fan in self.devices:
            if fan in data and "speed" in data[fan]:
                self.update_fan_speed(None, fan, self._printer.get_fan_speed(fan))

    def update_fan_speed(self, widget, fan, speed):
        if fan not in self.devices:
            return

        if self.devices[fan]["changeable"] is True:
            if self.devices[fan]["scale"].has_grab():
                return
            self.devices[fan]["speed"] = round(float(speed) * 100)
            self.devices[fan]["scale"].disconnect_by_func(self.set_fan_speed)
            self.devices[fan]["scale"].set_value(self.devices[fan]["speed"])
            self.devices[fan]["scale"].connect("button-release-event", self.set_fan_speed, fan)
        else:
            self.devices[fan]["speed"] = float(speed)
            self.devices[fan]["scale"].set_fraction(self.devices[fan]["speed"])
        if widget is not None:
            self.set_fan_speed(None, None, fan)

    def add_fan(self, fan, used_labels):

        logging.info(f"Adding fan: {fan}")
        changeable = any(fan.startswith(x) or fan == x for x in CHANGEABLE_FANS)
        name = Gtk.Label(
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=True,
            wrap=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
        )
        fan_name = _("Part Fan") if fan == "fan" else fan.split()[1]
        fan_cfg = self._printer.get_config_section(fan)
        cfg_alias = None
        if isinstance(fan_cfg, dict) and fan != "fan":
            cfg_alias = fan_cfg.get("friendly_name")
            if cfg_alias:
                cfg_alias = str(cfg_alias).strip()
        if fan != "fan":
            if cfg_alias:
                # friendly_name is the operator-facing name; keep it as-is
                # because the short-label mapping below cannot represent
                # non-ASCII or multi-word aliases.
                fan_name = cfg_alias
            elif fan.startswith("fan_generic"):
                # Only generic fans need compact labels (E1:, E2:, ...);
                # heater/controller fans keep their full config name since
                # this panel has enough room and short codes like MOT: are
                # harder to read than the original name.
                base = fan_name
                i = 1
                while i < len(base) and base[i].isdigit():
                    i += 1
                if i > 1 and base[0].isalpha():
                    fan_name = f"{base[:i].upper()}:"
                else:
                    base = base.split("_")[0].strip()
                    base = re.sub(r"[^A-Za-z0-9]+", "", base)
                    if not base:
                        fan_name = _("Fan") + ":"
                    else:
                        fan_name = base[:3].upper() + ":"
            if fan_name in used_labels:
                base_label = fan_name.rstrip(":")
                dup_idx = 2
                while f"{base_label}{dup_idx}:" in used_labels:
                    dup_idx += 1
                fan_name = f"{base_label}{dup_idx}:"
            used_labels.add(fan_name)
        name.set_markup(f"\n<big><b>{GLib.markup_escape_text(fan_name)}</b></big>\n")

        fan_col = Gtk.Box(spacing=5)
        stop_btn = self._gtk.Button("cancel", None, "color1")
        stop_btn.set_hexpand(False)
        stop_btn.connect("clicked", self.update_fan_speed, fan, 0)
        max_btn = self._gtk.Button("fan-on", _("Max"), "color2")
        max_btn.set_hexpand(False)
        max_btn.connect("clicked", self.update_fan_speed, fan, 100)

        speed = float(self._printer.get_fan_speed(fan))
        if changeable:
            speed = round(speed * 100)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, min=0, max=100, step=1)
            scale.set_value(speed)
            scale.set_digits(0)
            scale.set_hexpand(True)
            scale.set_has_origin(True)
            scale.get_style_context().add_class("fan_slider")
            scale.connect("button-release-event", self.set_fan_speed, fan)
            fan_col.add(stop_btn)
            fan_col.add(scale)
            fan_col.add(max_btn)
        else:
            scale = Gtk.ProgressBar(hexpand=True, show_text=True, fraction=speed)
            fan_col.pack_start(scale, True, True, 10)

        fan_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        fan_row.add(name)
        fan_row.add(fan_col)

        self.devices[fan] = {
            "changeable": changeable,
            "scale": scale,
            "speed": speed,
        }

        devices = sorted(self.devices)
        if fan == "fan":
            pos = 0
        elif "fan" in devices:
            devices.pop(devices.index("fan"))
            pos = devices.index(fan) + 1
        else:
            pos = devices.index(fan)

        self.labels["devices"].insert_row(pos)
        self.labels["devices"].attach(fan_row, 0, pos, 1, 1)
        self.labels["devices"].show_all()

    def load_fans(self):
        fans = self._printer.get_fans()
        used_labels = set()
        for fan in fans:
            # Support for hiding devices by name
            name = fan.split()[1] if len(fan.split()) > 1 else fan
            if name.startswith("_"):
                continue
            self.add_fan(fan, used_labels)

    def set_fan_speed(self, widget, event, fan):
        value = self.devices[fan]["scale"].get_value()

        if fan == "fan":
            self._screen._ws.api.gcode_script(f"M106 S{value * 2.55:.0f}")
        else:
            self._screen._ws.api.gcode_script(
                f"SET_FAN_SPEED FAN={fan.split()[1]} SPEED={float(value) / 100}"
            )
        # Check the speed in case it wasn't applied
        GLib.timeout_add_seconds(1, self.check_fan_speed, fan)

    def check_fan_speed(self, fan):
        self.update_fan_speed(None, fan, self._printer.get_fan_speed(fan))
        return False
