import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from ks_includes.offsetmap import OffsetMap
from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):
    bs_deltas = ["0.01", "0.05", "0.1"]
    bs_delta = bs_deltas[-1]

    def __init__(self, screen, title):
        title = title or _("Offset")
        super().__init__(screen, title)
        self.show_create = False
        self.active_mesh = None
        self.profiles = {}
        self.current_point = -1
        self.preheat_started = False
        self.save_in_progress = False
        offset_min = self._printer.get_stat("toolhead", "axis_minimum")
        offset_max = self._printer.get_stat("toolhead", "axis_maximum")
        if (
            not isinstance(offset_min, (list, tuple))
            or len(offset_min) < 2
            or not isinstance(offset_max, (list, tuple))
            or len(offset_max) < 2
        ):
            raise RuntimeError(_("Printer axis limits are unavailable"))
        self.offset_bm = [[[0, 0, 0] for _ in range(4)] for _ in range(4)]

        center_x = (offset_min[0] + offset_max[0]) / 2
        x_positions = [center_x - 75, center_x - 25, center_x + 25, center_x + 75]
        y_positions = [20.0, 73.33, 126.66, 179.99]
        self.probe_points = []
        self.record_position = []
        for row, y_pos in enumerate(y_positions):
            columns = range(4) if row % 2 == 0 else range(3, -1, -1)
            for column in columns:
                self.probe_points.append((x_positions[column], y_pos))
                self.record_position.append((row, column))
        if any(
            x_pos - 20 < offset_min[0]
            or x_pos + 20 > offset_max[0]
            or y_pos - 20 < offset_min[1]
            or y_pos + 20 > offset_max[1]
            for x_pos, y_pos in self.probe_points
        ):
            # Each cross extends 20 mm around its center; reject the workflow
            # before heating when this machine cannot contain the pattern.
            raise RuntimeError(_("Offset calibration pattern exceeds printer limits"))

        self.labels['x+'] = self._gtk.Button("arrow-right", "X+", "color2")
        self.labels['x-'] = self._gtk.Button("arrow-left", "X-", "color2")
        self.labels['xoffset'] = self._gtk.Button("refresh", '  0.00' + ("mm"),
                                                  "color2", self.bts, Gtk.PositionType.LEFT, 1)

        # Bundled themes expose color1-color4 only; color4 keeps these
        # controls visibly grouped instead of silently falling back to default.
        self.labels['y+'] = self._gtk.Button("arrow-up", "Y+", "color4")
        self.labels['y-'] = self._gtk.Button("arrow-down", "Y-", "color4")
        self.labels['yoffset'] = self._gtk.Button("refresh", '  0.00' + ("mm"),
                                                  "color4", self.bts, Gtk.PositionType.LEFT, 1)

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
            # Pass the raw string: label keys are built from it, and a float
            # like 1.0 produces "bdelta1.0" which does not exist (KeyError on
            # every click of an integer step button).
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

        topbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        topbar.set_hexpand(True)
        topbar.set_vexpand(False)

        # Create a grid for all profiles
        self.labels['profiles'] = Gtk.Grid()
        self.labels['profiles'].set_valign(Gtk.Align.CENTER)

        scroll = self._gtk.ScrolledWindow()
        scroll.add(self.labels['profiles'])
        scroll.set_vexpand(True)

        # KlippyGtk no longer provides HomogeneousGrid; create the equivalent
        # GTK grid directly so the custom offset panel survives upstream merges.
        grid = Gtk.Grid(column_homogeneous=True, row_homogeneous=False)

        self.labels['map'] = OffsetMap(self._gtk.font_size, self.active_mesh)
        if self._screen.vertical_mode:
            grid.attach(self.labels['map'], 0, 0, 3, 1)
            #            grid.attach(scroll, 0, 1, 2, 1)
            self.labels['map'].set_size_request(
                self._gtk.content_width, self._gtk.content_height * 0.4
            )
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

    def update_graph(self, widget=None, profile=None):
        self.labels['map'].update_bm(self.offset_bm)
        self.labels['map'].queue_draw()

    def back(self):
        # Skip redundant heater shutdown commands while a SAVE_CONFIG sequence is
        # in progress; that sequence already turns heaters off and triggers a
        # reconnect, so extra commands can fail and only create noisy logs.
        if self.save_in_progress:
            return False
        if self.preheat_started:
            self._screen._ws.api.gcode_script("M104 T0 S0")
            self._screen._ws.api.gcode_script("M104 T1 S0")
            if self._printer.config_section_exists("heater_bed"):
                self._screen._ws.api.gcode_script("M140 S0")
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
                offset = data["gcode_move"].get("offset_position")
                if isinstance(offset, (list, tuple)) and len(offset) >= 3:
                    self.labels["xoffset"].set_label(f"  {offset[0]:.2f}mm")
                    self.labels["yoffset"].set_label(f"  {offset[1]:.2f}mm")
                    self.labels["zoffset"].set_label(f"  {offset[2]:.3f}mm")
                    self._record_current_offset(offset)

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

    def Y_offset_adjustment(self, widget, direction):
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

    def Z_offset_adjustment(self, widget, direction):
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

    def send_next_offset(self, widget):
        next_point = self.current_point + 1
        if next_point >= len(self.probe_points):
            self._screen.show_popup_message(_("All offset points have been completed"), level=1)
            self.labels["next"].set_sensitive(False)
            return

        absolute_coordinates = self._printer.get_stat(
            "gcode_move", "absolute_coordinates"
        )
        absolute_extrude = self._printer.get_stat("gcode_move", "absolute_extrude")
        if not isinstance(absolute_coordinates, bool) or not isinstance(
            absolute_extrude, bool
        ):
            # Guessing a missing modal state can leave later print commands in
            # G91 or the wrong extrusion mode, so wait for subscription data.
            self._screen.show_popup_message(_("Printer movement state is unavailable"), level=2)
            return

        # Opening a panel must not move or heat the printer.  Start the
        # calibration preparation only after the user explicitly presses Next.
        if self._printer.get_stat("toolhead", "homed_axes") != "xyz":
            self._screen._ws.api.gcode_script("G28")
        if not self.preheat_started:
            self._screen._ws.api.gcode_script("M104 T0 S200")
            self._screen._ws.api.gcode_script("M104 T1 S200")
            if self._printer.config_section_exists("heater_bed"):
                self._screen._ws.api.gcode_script("M140 S60")
            self.preheat_started = True

        if float(self._printer.get_stat("extruder", "temperature") or 0) < 195:
            self._screen.show_popup_message(_("Nozzle 1 temperature below 200 °C"))
            return
        if self._printer.config_section_exists("extruder1"):
            if float(self._printer.get_stat("extruder1", "temperature") or 0) < 195:
                self._screen.show_popup_message(_("Nozzle 2 temperature below 200 °C"))
                return
        if self._printer.config_section_exists("heater_bed"):
            if float(self._printer.get_stat("heater_bed", "temperature") or 0) < 55:
                self._screen.show_popup_message(_("Hot bed temperature below 60 °C"))
                return
        self.current_point = next_point
        point_x, point_y = self.probe_points[self.current_point]
        restore_xyz = "" if absolute_coordinates else "\nG91"
        restore_e = "M82" if absolute_extrude else "M83"
        # Submit one ordered script so another UI action cannot interleave with
        # the two tool patterns.  Restore the caller's XYZ/E modal state.
        script = f"""M83
G90
G1 Z3 F1000
T0
G0 X{point_x - 20} Y{point_y} F3000
G1 Z0.25 F1000
G1 E5 F500
G1 X{point_x} Y{point_y} E2 F1000
G1 X{point_x} Y{point_y + 20} E2 F1000
G1 X{point_x} Y{point_y} E2 F1000
G1 X{point_x - 20} Y{point_y} E2 F1000
G1 E-4 F3000
G1 Z3 F1000
T1
G0 X{point_x + 20} Y{point_y} F3000
G1 Z0.25 F1000
G1 E5 F500
G1 X{point_x} Y{point_y} E2 F1000
G1 X{point_x} Y{point_y - 20} E2 F1000
G1 X{point_x} Y{point_y} E2 F1000
G1 X{point_x + 20} Y{point_y} E2 F1000
G1 E-4 F3000
G1 Z3 F1000
T0
{restore_e}{restore_xyz}"""
        self._screen._ws.api.gcode_script(script)

        if self.current_point == len(self.probe_points) - 1:
            self.labels["next"].set_sensitive(False)

    def send_save_offset(self, widget):
        if self.save_in_progress:
            # The first Finish press already sent the apply + SAVE_CONFIG
            # script and klippy is restarting; a second copy racing that
            # restart produced the 2026-08-20 "Internal error on
            # command:SAVE_CONFIG" shutdown (klippy.log backups
            # printer-20260820_101037/101039.cfg).  activate() clears the
            # flag when the panel is shown again after the screen reconnects.
            self._screen.show_popup_message(
                _("Configuration is being saved, please wait"), level=1
            )
            return
        self._record_current_offset(
            self._printer.get_stat("gcode_move", "offset_position")
        )
        if "E_OFFSET_APPLY_PROBE" in self._printer.available_commands:
            apply_command = "E_OFFSET_APPLY_PROBE"
        elif "E_OFFSET_APPLY_ENDSTOP" in self._printer.available_commands:
            apply_command = "E_OFFSET_APPLY_ENDSTOP"
        else:
            self._screen.show_popup_message(_("No offset save command is available"), level=2)
            return
        # The apply command only stages configfile values.  SAVE_CONFIG is
        # required to persist the calibrated nozzle geometry across restarts.
        self.save_in_progress = True
        script = [
            "M104 T0 S0",
            "M104 T1 S0",
        ]
        if self._printer.config_section_exists("heater_bed"):
            script.append("M140 S0")
        script.append(apply_command)
        script.append("SAVE_CONFIG")
        self._screen._ws.api.gcode_script("\n".join(script))
        # klippy restarts and the websocket reconnects several seconds later;
        # lock the workflow buttons and say so, otherwise the silent wait
        # looks like an ignored press and invites a duplicate.
        self.labels["finish"].set_sensitive(False)
        self.labels["next"].set_sensitive(False)
        self._screen.show_popup_message(
            _("Saving configuration, printer will restart"), level=1
        )

    def activate(self):
        # Re-entering the panel means the SAVE_CONFIG restart finished (or
        # never started); re-arm the Finish workflow.
        self.save_in_progress = False
        self.labels["finish"].set_sensitive(True)
        self.labels["next"].set_sensitive(True)

    def send_remove_offset(self, widget):
        self.current_point = -1
        self.labels["next"].set_sensitive(True)
        self.offset_bm = [[[0, 0, 0] for _ in range(4)] for _ in range(4)]
        self.update_graph()

    def _record_current_offset(self, offset):
        if self.current_point < 0 or not isinstance(offset, (list, tuple)):
            return
        if len(offset) < 3:
            return
        row, column = self.record_position[self.current_point]
        # Status updates arrive after the queued motion.  Recording them here
        # keeps each displayed cell aligned with the point the user adjusted.
        self.offset_bm[row][column] = list(offset[:3])

    def change_bs_delta(self, widget, bs):
        logging.info(f"### BabyStepping {bs}")
        self.labels[f"bdelta{self.bs_delta}"].get_style_context().remove_class("distbutton_active")
        self.labels[f"bdelta{bs}"].get_style_context().add_class("distbutton_active")
        self.bs_delta = bs
