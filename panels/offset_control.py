import logging
import contextlib

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from ks_includes.KlippyGcodes import KlippyGcodes
from ks_includes.screen_panel import ScreenPanel
from ks_includes.widgets.bedmap import BedMap
from ks_includes.widgets.offsetmap import OffsetMap

Current_point = 0


def create_panel(*args):
    return OffsetPanel(*args)


class OffsetPanel(ScreenPanel):
    bs_deltas = ["0.01", "0.05", "0.1"]
    bs_delta = bs_deltas[-1]

    def __init__(self, screen, title):
        global Current_point
        super().__init__(screen, title)
        self.show_create = False
        self.active_mesh = None
        self.profiles = {}
        Current_point = 0
        offset_max = self._printer.get_stat("toolhead", "axis_maximum")
        self.offset_bm = [[[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
                          [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
                          [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
                          [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]]]

        self.probe_points = [(offset_max[0]/2-75, 20.0), (offset_max[0]/2-25, 20.0), (offset_max[0]/2+25, 20.0), (offset_max[0]/2+75, 20.0),
                             (offset_max[0]/2+75, 73.33), (offset_max[0]/2+25, 73.33), (offset_max[0]/2-25, 73.33), (offset_max[0]/2-75, 73.33),
                             (offset_max[0]/2-75, 126.66), (offset_max[0]/2-25, 126.66), (offset_max[0]/2+25, 126.66), (offset_max[0]/2+75, 126.66),
                             (offset_max[0]/2+75, 179.99), (offset_max[0]/2+25, 179.99), (offset_max[0]/2-25, 179.99), (offset_max[0]/2-75, 179.99)]

        self.record_position = [(0, 0), (0, 1), (0, 2), (0, 3),
                                (1, 3), (1, 2), (1, 1), (1, 0),
                                (2, 0), (2, 1), (2, 2), (2, 3),
                                (3, 3), (3, 2), (3, 1), (3, 0)]

        self.labels['x+'] = self._gtk.Button("arrow-right", "X+", "color2")
        self.labels['x-'] = self._gtk.Button("arrow-left", "X-", "color2")
        self.labels['xoffset'] = self._gtk.Button("refresh", '  0.00' + ("mm"),
                                                  "color2", self.bts, Gtk.PositionType.LEFT, 1)

        self.labels['y+'] = self._gtk.Button("arrow-up", "Y+", "color5")
        self.labels['y-'] = self._gtk.Button("arrow-down", "Y-", "color5")
        self.labels['yoffset'] = self._gtk.Button("refresh", '  0.00' + ("mm"),
                                                  "color5", self.bts, Gtk.PositionType.LEFT, 1)

        self.labels['z+'] = self._gtk.Button("z-farther", "Z+", "color1")
        self.labels['z-'] = self._gtk.Button("z-closer", "Z-", "color1")
        self.labels['zoffset'] = self._gtk.Button("refresh", '  0.00' + ("mm"),
                                                  "color1", self.bts, Gtk.PositionType.LEFT, 1)

        self.labels['next'] = self._gtk.Button("arrow-right", _("Next"), "color3")
        self.labels['finish'] = self._gtk.Button("complete", _("Finish"), "color3")
        self.labels['clear'] = self._gtk.Button("cancel", _("Clear"), "color3")

        self.labels['x+'].connect("clicked", self.X_offset_adjustment, "+")
        self.labels['xoffset'].connect("clicked", self.X_offset_adjustment, "reset")
        self.labels['x-'].connect("clicked", self.X_offset_adjustment, "-")

        self.labels['y+'].connect("clicked", self.Y_offset_adjustment, "+")
        self.labels['yoffset'].connect("clicked", self.Y_offset_adjustment, "reset")
        self.labels['y-'].connect("clicked", self.Y_offset_adjustment, "-")

        self.labels['z+'].connect("clicked", self.Z_offset_adjustment, "+")
        self.labels['zoffset'].connect("clicked", self.Z_offset_adjustment, "reset")
        self.labels['z-'].connect("clicked", self.Z_offset_adjustment, "-")

        self.labels['next'].connect("clicked", self.send_next_offset)
        self.labels['finish'].connect("clicked", self.send_save_offset)
        self.labels['clear'].connect("clicked", self.send_remove_offset)

        bsgrid = Gtk.Grid()
        for j, i in enumerate(self.bs_deltas):
            self.labels[f"bdelta{i}"] = self._gtk.Button(label=i)
            self.labels[f"bdelta{i}"].connect("clicked", self.change_bs_delta, float(i))
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

        topbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        topbar.set_hexpand(True)
        topbar.set_vexpand(False)

        # Create a grid for all profiles
        self.labels['profiles'] = Gtk.Grid()
        self.labels['profiles'].set_valign(Gtk.Align.CENTER)

        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.labels['profiles'])
        scroll.set_vexpand(True)

        grid = self._gtk.HomogeneousGrid()
        grid.set_row_homogeneous(False)

        self.labels['map'] = OffsetMap(self._gtk.font_size, self.active_mesh)
        if self._screen.vertical_mode:
            grid.attach(self.labels['map'], 0, 0, 3, 1)
            #            grid.attach(scroll, 0, 1, 2, 1)
            self.labels['map'].set_size_request(self._gtk.content_width, self._gtk.content_height * .4)
        else:
            grid.attach(self.labels['map'], 0, 0, 2, 5)
        #            grid.attach(scroll, 1, 0, 1, 1)
        self.labels['main_grid'] = grid
        self.content.add(self.labels['main_grid'])

        #        grid.attach(topbar, 1, 0, 1, 1)
        if self._screen.vertical_mode:
            grid.attach(self.labels['next'], 0, 1, 1, 1)
            grid.attach(self.labels['finish'], 1, 1, 1, 1)
            grid.attach(self.labels['clear'], 2, 1, 1, 1)

            grid.attach(self.labels['x+'], 1, 2, 1, 1)
            grid.attach(self.labels['x-'], 2, 2, 1, 1)
            grid.attach(self.labels['xoffset'], 0, 2, 1, 1)

            grid.attach(self.labels['y+'], 1, 3, 1, 1)
            grid.attach(self.labels['y-'], 2, 3, 1, 1)
            grid.attach(self.labels['yoffset'], 0, 3, 1, 1)

            grid.attach(self.labels['z+'], 1, 4, 1, 1)
            grid.attach(self.labels['z-'], 2, 4, 1, 1)
            grid.attach(self.labels['zoffset'], 0, 4, 1, 1)
            grid.attach(bsgrid, 0, 5, 3, 1)

        else:
            grid.attach(self.labels['next'], 2, 0, 1, 1)
            grid.attach(self.labels['finish'], 3, 0, 1, 1)
            grid.attach(self.labels['clear'], 4, 0, 1, 1)

            grid.attach(self.labels['x+'], 3, 1, 1, 1)
            grid.attach(self.labels['x-'], 4, 1, 1, 1)
            grid.attach(self.labels['xoffset'], 2, 1, 1, 1)

            grid.attach(self.labels['y+'], 3, 2, 1, 1)
            grid.attach(self.labels['y-'], 4, 2, 1, 1)
            grid.attach(self.labels['yoffset'], 2, 2, 1, 1)

            grid.attach(self.labels['z+'], 3, 3, 1, 1)
            grid.attach(self.labels['z-'], 4, 3, 1, 1)
            grid.attach(self.labels['zoffset'], 2, 3, 1, 1)
            grid.attach(bsgrid, 2, 4, 3, 1)

        self._screen._ws.klippy.gcode_script("G28")
        self._screen._ws.klippy.gcode_script("M104 T0 S200")
        self._screen._ws.klippy.gcode_script("M104 T1 S200")
        self._screen._ws.klippy.gcode_script("M140 S60")

    def update_graph(self, widget=None, profile=None):
        self.labels['map'].update_bm(self.offset_bm)
        self.labels['map'].queue_draw()

    def back(self):
        self._screen._ws.klippy.gcode_script("M104 T0 S0")
        self._screen._ws.klippy.gcode_script("M104 T1 S0")
        self._screen._ws.klippy.gcode_script("M140 S0")
        if self.show_create is True:
            self.remove_create()
            return True
        return False

    def process_update(self, action, data):
        self.update_graph()
        if action != "notify_status_update":
            return

        if "gcode_move" in data:
            if self._printer.config_section_exists("extruder1"):
                if "offset_position" in data["gcode_move"]:
                    self.labels['zoffset'].set_label(f'  {data["gcode_move"]["offset_position"][2]:.3f}mm')
                if "offset_position" in data["gcode_move"]:
                    self.labels['xoffset'].set_label(f'  {data["gcode_move"]["offset_position"][0]:.2f}mm')
                if "offset_position" in data["gcode_move"]:
                    self.labels['yoffset'].set_label(f'  {data["gcode_move"]["offset_position"][1]:.2f}mm')

    def remove_create(self):
        if self.show_create is False:
            return

        self._screen.remove_keyboard()
        for child in self.content.get_children():
            self.content.remove(child)

        self.show_create = False
        self.content.add(self.labels['main_grid'])
        self.content.show()

    def X_offset_adjustment(self, widget, direction):
        if direction == "reset":
            self.labels['xoffset'].set_label('  0.00mm')
            self._screen._ws.klippy.gcode_script("SET_GCODE_EOFFSET X=0 MOVE=1")
        elif direction in ["+", "-"]:
            with contextlib.suppress(KeyError):
                x_offset = float(self._printer.data["gcode_move"]["offset_position"][0])
                if direction == "+":
                    x_offset += float(self.bs_delta)
                else:
                    x_offset -= float(self.bs_delta)
                self.labels['xoffset'].set_label(f'  {x_offset:.3f}mm')
            self._screen._ws.klippy.gcode_script(f"SET_GCODE_EOFFSET X_ADJUST={direction}{self.bs_delta} MOVE=1")

    def Y_offset_adjustment(self, widget, direction):
        if direction == "reset":
            self.labels['yoffset'].set_label('  0.00mm')
            self._screen._ws.klippy.gcode_script("SET_GCODE_EOFFSET Y=0 MOVE=1")
        elif direction in ["+", "-"]:
            with contextlib.suppress(KeyError):
                y_offset = float(self._printer.data["gcode_move"]["offset_position"][1])
                if direction == "+":
                    y_offset += float(self.bs_delta)
                else:
                    y_offset -= float(self.bs_delta)
                self.labels['yoffset'].set_label(f'  {y_offset:.3f}mm')
            self._screen._ws.klippy.gcode_script(f"SET_GCODE_EOFFSET Y_ADJUST={direction}{self.bs_delta} MOVE=1")

    def Z_offset_adjustment(self, widget, direction):
        if direction == "reset":
            self.labels['zoffset'].set_label('  0.00mm')
            self._screen._ws.klippy.gcode_script("SET_GCODE_EOFFSET Z=0 MOVE=1")
        elif direction in ["+", "-"]:
            with contextlib.suppress(KeyError):
                z_offset = float(self._printer.data["gcode_move"]["offset_position"][2])
                if direction == "+":
                    z_offset += float(self.bs_delta)
                else:
                    z_offset -= float(self.bs_delta)
                self.labels['zoffset'].set_label(f'  {z_offset:.3f}mm')
            self._screen._ws.klippy.gcode_script(f"SET_GCODE_EOFFSET Z_ADJUST={direction}{self.bs_delta} MOVE=1")

    def send_next_offset(self, widget):
        global Current_point
        if self._printer.get_dev_stat('extruder', "temperature") < 195:
            self._screen.show_popup_message(_("Nozzle 1 temperature below 200℃"))
            return
        if self._printer.config_section_exists("extruder1"):
            if self._printer.get_dev_stat('extruder1', "temperature") < 195:
                self._screen.show_popup_message(_("Nozzle 1 temperature below 200℃"))
                return
        if self._printer.config_section_exists("heater_bed"):
            if self._printer.get_dev_stat('heater_bed', "temperature") < 55:
                self._screen.show_popup_message(_("Hot bed temperature below 60℃"))
                return
        self._screen._ws.klippy.gcode_script("M83")
        self._screen._ws.klippy.gcode_script("G1 Z3 F1000")
        self._screen._ws.klippy.gcode_script("T0")
        for i in range(1):
            self._screen._ws.klippy.gcode_script(
                f"G0 X{self.probe_points[Current_point][0] - 20} Y{self.probe_points[Current_point][1]} F3000")
            self._screen._ws.klippy.gcode_script("G1 Z0.25 F1000")
            self._screen._ws.klippy.gcode_script("G1 E5 F500")
            self._screen._ws.klippy.gcode_script(
                f"G1 X{self.probe_points[Current_point][0]} Y{self.probe_points[Current_point][1]} E2 F1000")
            self._screen._ws.klippy.gcode_script(
                f"G1 X{self.probe_points[Current_point][0]} Y{self.probe_points[Current_point][1] + 20} E2 F1000")

            self._screen._ws.klippy.gcode_script(
                f"G1 X{self.probe_points[Current_point][0]} Y{self.probe_points[Current_point][1]} E2 F1000")
            self._screen._ws.klippy.gcode_script(
                f"G1 X{self.probe_points[Current_point][0] - 20} Y{self.probe_points[Current_point][1]} E2 F1000")
            self._screen._ws.klippy.gcode_script("G1 E-4 F3000")

        self._screen._ws.klippy.gcode_script("G1 Z3 F1000")
        self._screen._ws.klippy.gcode_script("T1")
        for i in range(1):
            self._screen._ws.klippy.gcode_script(
                f"G0 X{self.probe_points[Current_point][0] + 20} Y{self.probe_points[Current_point][1]} F3000")
            self._screen._ws.klippy.gcode_script("G1 Z0.25 F1000")
            self._screen._ws.klippy.gcode_script("G1 E5 F500")   
            self._screen._ws.klippy.gcode_script(
                f"G1 X{self.probe_points[Current_point][0]} Y{self.probe_points[Current_point][1]} E2 F1000")
            self._screen._ws.klippy.gcode_script(
                f"G1 X{self.probe_points[Current_point][0]} Y{self.probe_points[Current_point][1] - 20} E2 F1000")

            self._screen._ws.klippy.gcode_script(
                f"G1 X{self.probe_points[Current_point][0]} Y{self.probe_points[Current_point][1]} E2 F1000")
            self._screen._ws.klippy.gcode_script(
                f"G1 X{self.probe_points[Current_point][0] + 20} Y{self.probe_points[Current_point][1]} E2 F1000")
            self._screen._ws.klippy.gcode_script("G1 E-4 F3000")

        self._screen._ws.klippy.gcode_script("G1 Z3 F1000")
        self._screen._ws.klippy.gcode_script("T0")

        x_point = self.record_position[Current_point][0]
        y_point = self.record_position[Current_point][1]
        self.offset_bm[x_point][y_point][0] = self._printer.data["gcode_move"]["offset_position"][0]
        self.offset_bm[x_point][y_point][1] = self._printer.data["gcode_move"]["offset_position"][1]
        self.offset_bm[x_point][y_point][2] = self._printer.data["gcode_move"]["offset_position"][2]
        Current_point += 1

    def send_save_offset(self, widget):
        endstop = (self._printer.config_section_exists("stepper_z") and
                    not self._printer.get_config_section("stepper_z")['endstop_pin'].startswith("probe"))
        if endstop == 0:
            self._screen._ws.klippy.gcode_script("E_OFFSET_APPLY_PROBE")
        else:
            self._screen._ws.klippy.gcode_script("E_OFFSET_APPLY_ENDSTOP")

    def send_remove_offset(self, widget):
        global Current_point
        Current_point = 0
        self.offset_bm = [[[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
                          [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
                          [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
                          [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]]]

    def change_bs_delta(self, widget, bs):
        logging.info(f"### BabyStepping {bs}")
        self.labels[f"bdelta{self.bs_delta}"].get_style_context().remove_class("distbutton_active")
        self.labels[f"bdelta{bs}"].get_style_context().add_class("distbutton_active")
        self.bs_delta = bs
