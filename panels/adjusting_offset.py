import ast
import configparser
import logging
import os
import re

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    bs_deltas = ["0.01", "0.05", "0.1", "0.5", "1"]
    bs_delta = bs_deltas[-1]

    def __init__(self, screen, title):
        title = title or _("Adjusting offset")
        super().__init__(screen, title)
        if self.ks_printer_cfg is not None:
            bs = self.ks_printer_cfg.get("z_babystep_values", "0.01, 0.05")
            if re.match(r'^[0-9,\.\s]+$', bs):
                bs = [str(i.strip()) for i in bs.split(',')]
                if 1 < len(bs) < 3:
                    self.bs_deltas = bs
                    self.bs_delta = self.bs_deltas[-1]

        self.double_print_mark = self.check_copy_mode()
        # babystepping grid
        bsgrid = Gtk.Grid()
        for j, i in enumerate(self.bs_deltas):
            self.labels[f"bdelta{i}"] = self._gtk.Button(label=i)
            # Pass the raw string: label keys are built from it, and a float
            # like 1.0 produces "bdelta1.0" which does not exist (KeyError on
            # every click of the "1" step button).
            self.labels[f"bdelta{i}"].connect("clicked", self.change_bs_delta, i)
            ctx = self.labels[f"bdelta{i}"].get_style_context()
            if j == 0:
                ctx.add_class("distbutton_top")
            elif j == len(self.bs_deltas) - 1:
                ctx.add_class("distbutton_bottom")
            else:
                ctx.add_class("distbutton")
            if i == self.bs_delta:
                ctx.add_class("distbutton_active")
            bsgrid.attach(self.labels[f"bdelta{i}"], j, 0, 1, 1)

        # KlippyGtk no longer provides HomogeneousGrid; create the equivalent
        # GTK grid directly so this custom panel remains loadable after merges.
        grid = Gtk.Grid(column_homogeneous=True, row_homogeneous=False)

        self.labels['x+'] = self._gtk.Button("arrow-right", "X+", "color3")
        self.labels['x-'] = self._gtk.Button("arrow-left", "X-", "color3")
        self.labels['xoffset'] = self._gtk.Button("refresh", '  0.00' + _("mm"),
                                                "color3", self.bts, Gtk.PositionType.LEFT, 1)
        
        self.labels['y+'] = self._gtk.Button("arrow-up", "Y+", "color4")
        self.labels['y-'] = self._gtk.Button("arrow-down", "Y-", "color4")
        self.labels['yoffset'] = self._gtk.Button("refresh", '  0.00' + _("mm"),
                                                "color4", self.bts, Gtk.PositionType.LEFT, 1)

        self.labels['z+'] = self._gtk.Button("z-farther", "Z+", "color1")
        self.labels['z-'] = self._gtk.Button("z-closer", "Z-", "color1")
        self.labels['zoffset'] = self._gtk.Button("refresh", '  0.00' + _("mm"),
                                                  "color1", self.bts, Gtk.PositionType.LEFT, 1)
        if self._screen.vertical_mode:
            grid.attach(self.labels['x+'], 0, 0, 1, 1)
            grid.attach(self.labels['x-'], 1, 0, 1, 1)
            grid.attach(self.labels['xoffset'], 2, 0, 1, 1)
            grid.attach(bsgrid, 0, 1, 3, 1)
            grid.attach(self.labels['y+'], 0, 2, 1, 1)
            grid.attach(self.labels['y-'], 1, 2, 1, 1)
            grid.attach(self.labels['yoffset'], 2, 2, 1, 1)
            grid.attach(self.labels['z+'], 0, 3, 1, 1)
            grid.attach(self.labels['z-'], 1, 3, 1, 1)
            grid.attach(self.labels['zoffset'], 2, 3, 1, 1)
        else:
            grid.attach(self.labels['xoffset'], 0, 0, 1, 1)
            grid.attach(self.labels['x+'], 0, 1, 1, 1)
            grid.attach(self.labels['x-'], 0, 2, 1, 1)
            grid.attach(bsgrid, 0, 3, 3, 1)
            grid.attach(self.labels['yoffset'], 1, 0, 1, 1)
            grid.attach(self.labels['y+'], 1, 1, 1, 1)
            grid.attach(self.labels['y-'], 1, 2, 1, 1)
            grid.attach(self.labels['zoffset'], 2, 0, 1, 1)
            grid.attach(self.labels['z+'], 2, 1, 1, 1)
            grid.attach(self.labels['z-'], 2, 2, 1, 1)

        self.labels['z+'].connect("clicked", self.change_babystepping_z, "+")
        self.labels['zoffset'].connect("clicked", self.change_babystepping_z, "reset")
        self.labels['z-'].connect("clicked", self.change_babystepping_z, "-")

        self.labels['x+'].connect("clicked", self.change_babystepping_x, "+")
        self.labels['xoffset'].connect("clicked", self.change_babystepping_x, "reset")
        self.labels['x-'].connect("clicked", self.change_babystepping_x, "-")

        self.labels['y+'].connect("clicked", self.change_babystepping_y, "+")
        self.labels['yoffset'].connect("clicked", self.change_babystepping_y, "reset")
        self.labels['y-'].connect("clicked", self.change_babystepping_y, "-")

        self.content.add(grid)

        if self.double_print_mark:
            self.set_copy_mode(True)
        else:
            self.set_copy_mode(False)

    def check_copy_mode(self):
        allvars = {}
        varfile = configparser.ConfigParser(interpolation=None)
        poweroff_path = self._screen.poweroff_data_path
        if os.path.exists(poweroff_path):
            try:
                varfile.read(poweroff_path)
                if varfile.has_section('Variables'):
                    for name, val in varfile.items('Variables'):
                        allvars[name] = ast.literal_eval(val)
                print_mode = allvars.get("print_mode")
                if isinstance(print_mode, str) and "PRIMARY_MODE" not in print_mode:
                    return True
            except (OSError, ValueError, SyntaxError, configparser.Error) as err:
                logging.warning("Unable to read print mode from %s: %s", poweroff_path, err)

        return False

    def set_copy_mode(self, enabled):
        buttons = ['x+', 'x-', 'xoffset', 'y+', 'y-', 'yoffset', 'z+', 'z-', 'zoffset']
        buttons.extend([f"bdelta{i}" for i in self.bs_deltas])

        for button in buttons:
            self.labels[button].set_sensitive(not enabled)
            if enabled:
                self.labels[button].get_style_context().add_class("disabled")
            else:
                self.labels[button].get_style_context().remove_class("disabled")
        if enabled:
            self._screen.show_popup_message(
                _("Offset cannot be adjusted in copy mode or mirror mode"), level=1
            )


    def process_update(self, action, data):

        if action != "notify_status_update":
            return

        if "gcode_move" in data:
            offset = data["gcode_move"].get("offset_position")
            if isinstance(offset, (list, tuple)) and len(offset) >= 3:
                for axis, index in (("x", 0), ("y", 1), ("z", 2)):
                    self.labels[f"{axis}offset"].set_label(f"  {offset[index]:.3f}mm")

    def change_babystepping_z(self, widget, direction):
        if direction == "reset":
            self.labels['zoffset'].set_label('  0.00mm')
            self._screen._ws.api.gcode_script("SET_GCODE_EOFFSET Z=0 MOVE=1")
        elif direction in ["+", "-"]:
            offset = self._printer.get_stat("gcode_move", "offset_position")
            if isinstance(offset, (list, tuple)) and len(offset) >= 3:
                z_offset = float(offset[2])
                if direction == "+":
                    z_offset += float(self.bs_delta)
                else:
                    z_offset -= float(self.bs_delta)
                self.labels['zoffset'].set_label(f'  {z_offset:.3f}mm')
            self._screen._ws.api.gcode_script(
                f"SET_GCODE_EOFFSET Z_ADJUST={direction}{self.bs_delta} MOVE=1"
            )

    def change_babystepping_x(self, widget, direction):
        if direction == "reset":
            self.labels['xoffset'].set_label('  0.00mm')
            self._screen._ws.api.gcode_script("SET_GCODE_EOFFSET X=0 MOVE=1")
        elif direction in ["+", "-"]:
            offset = self._printer.get_stat("gcode_move", "offset_position")
            if isinstance(offset, (list, tuple)) and len(offset) >= 3:
                x_offset = float(offset[0])
                if direction == "+":
                    x_offset += float(self.bs_delta)
                else:
                    x_offset -= float(self.bs_delta)
                self.labels['xoffset'].set_label(f'  {x_offset:.3f}mm')
            self._screen._ws.api.gcode_script(
                f"SET_GCODE_EOFFSET X_ADJUST={direction}{self.bs_delta} MOVE=1"
            )

    def change_babystepping_y(self, widget, direction):
        if direction == "reset":
            self.labels['yoffset'].set_label('  0.00mm')
            self._screen._ws.api.gcode_script("SET_GCODE_EOFFSET Y=0 MOVE=1")
        elif direction in ["+", "-"]:
            offset = self._printer.get_stat("gcode_move", "offset_position")
            if isinstance(offset, (list, tuple)) and len(offset) >= 3:
                y_offset = float(offset[1])
                if direction == "+":
                    y_offset += float(self.bs_delta)
                else:
                    y_offset -= float(self.bs_delta)
                self.labels['yoffset'].set_label(f'  {y_offset:.3f}mm')
            self._screen._ws.api.gcode_script(
                f"SET_GCODE_EOFFSET Y_ADJUST={direction}{self.bs_delta} MOVE=1"
            )

    def change_bs_delta(self, widget, bs):
        logging.info(f"### BabyStepping {bs}")
        self.labels[f"bdelta{self.bs_delta}"].get_style_context().remove_class("distbutton_active")
        self.labels[f"bdelta{bs}"].get_style_context().add_class("distbutton_active")
        self.bs_delta = bs

