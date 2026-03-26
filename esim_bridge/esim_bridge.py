# esim_bridge.py

import pcbnew
import wx
import os
import subprocess
import re
import shutil
import logging
import traceback
import tempfile
from datetime import datetime


# Add this class ABOVE the ESimBridgePlugin class

class SPICEConverter:
    """
    Converts KiCad netlist data into a SPICE deck (.cir file)
    that Ngspice/eSim can simulate.
    """
    
    def __init__(self):
        # Map of KiCad reference prefixes to SPICE element types
        # KiCad uses R1, C1, L1, U1 etc.
        # SPICE needs to know the element type from the first letter
        self.supported_types = {
            'R': 'resistor',
            'C': 'capacitor', 
            'L': 'inductor',
            'V': 'voltage_source',
            'I': 'current_source',
            'D': 'diode',
            'Q': 'bjt_transistor',
            'M': 'mosfet',
            'U': 'ic_subcircuit',
            'X': 'subcircuit',
        }
    
    def convert(self, netlist_path, output_path, analysis_type='tran',
                analysis_params=None):
        """
        Main conversion function.
        
        Args:
            netlist_path: Path to KiCad .net file
            output_path: Where to save the .cir SPICE file
            analysis_type: 'tran', 'ac', or 'dc'
            analysis_params: dict with analysis parameters
        
        Returns:
            True if successful, False if failed
        """
        try:
            # Read and parse the netlist
            components, nets = self.parse_full_netlist(netlist_path)
            
            if not components:
                return False
            
            # Build SPICE content
            spice_lines = []
            
            # Header comment
            spice_lines.append(
                "* eSim Bridge Plugin - Auto-generated SPICE file"
            )
            spice_lines.append(
                f"* Source: {netlist_path}"
            )
            spice_lines.append("")
            
            # Component lines
            spice_lines.append("* Components")
            for ref, comp_data in components.items():
                spice_line = self.component_to_spice(ref, comp_data, nets)
                if spice_line:
                    spice_lines.append(spice_line)
            
            spice_lines.append("")
            
            # Auto-inject generic diode model if any diode present
            has_diode = any(ref.startswith('D') for ref in components)
            if has_diode:
                spice_lines.append("* Generic LED/Diode model (auto-injected by P-BRIDGE)")
                spice_lines.append(".model dled D(Is=2.52e-9 N=1.752 Rs=0.568 Cjo=825e-12 Bv=30 Ibv=10e-6)")
                spice_lines.append("")
            
            # Analysis command
            spice_lines.append("* Simulation Analysis")
            analysis_cmd = self.get_analysis_command(
                analysis_type, analysis_params
            )
            spice_lines.append(analysis_cmd)
            spice_lines.append("")
            
            # Print/plot commands
            spice_lines.append("* Output")
            output_cmds = self.get_output_commands(nets, analysis_type)
            spice_lines.extend(output_cmds)
            spice_lines.append("")
            
            # End of SPICE file (MANDATORY)
            spice_lines.append(".end")
            
            # Write to file
            with open(output_path, 'w') as f:
                f.write('\n'.join(spice_lines) + '\n')
            
            return True
            
        except Exception as e:
            print(f"SPICE conversion error: {e}")
            return False
    
    def parse_full_netlist(self, netlist_path):
        """
        Parse KiCad netlist file.
        Returns:
            components: {ref: {value, pins: {pin_num: net_name}}}
            nets: {net_name: [list of (ref, pin) connections]}
        """
        components = {}
        nets = {}
        
        with open(netlist_path, 'r') as f:
            content = f.read()
        
        # Parse components section
        # Find each (comp ...) block
        comp_blocks = re.findall(
            r'\(comp\s+\(ref\s+"([^"]+)"\)(.*?)\)\s*\n\s*\(',
            content, 
            re.DOTALL
        )
        
        # Better approach: split by (comp and parse each block
        parts = content.split('(comp ')
        
        for part in parts[1:]:  # Skip first part (before any comp)
            # Extract reference
            ref_match = re.search(r'\(ref\s+"([^"]+)"\)', part)
            if not ref_match:
                continue
            ref = ref_match.group(1)
            
            # Extract value
            val_match = re.search(r'\(value\s+"([^"]+)"\)', part)
            value = val_match.group(1) if val_match else "?"
            
            # Extract description (optional)
            desc_match = re.search(r'\(description\s+"([^"]+)"\)', part)
            description = desc_match.group(1) if desc_match else ""
            
            
            # Extract Sim.Type and Sim.Params for simulation sources
            sim_type_match = re.search(r'\(property\s+\(name\s+"Sim\.Type"\)\s+\(value\s+"([^"]+)"\)', part)
            sim_params_match = re.search(r'\(property\s+\(name\s+"Sim\.Params"\)\s+\(value\s+"([^"]+)"\)', part)

            sim_type = sim_type_match.group(1) if sim_type_match else ""
            sim_params = sim_params_match.group(1) if sim_params_match else ""

            components[ref] = {
                'value': value,
                'description': description,
                'sim_type': sim_type,
                'sim_params': sim_params,
                'pins': {}
            }
            

        # Parse nets section to get connections
        # Find each (net ...) block
        net_parts = content.split('(net ')
        
        for part in net_parts[1:]:
            # Extract net name
            name_match = re.search(r'\(name\s+"([^"]+)"\)', part)
            if not name_match:
                continue
            net_name = name_match.group(1)
            
            # Clean net name for SPICE (no special characters)
            spice_net = self.clean_net_name(net_name)
            
            nets[net_name] = {
                'spice_name': spice_net,
                'nodes': []
            }
            
            # Find all nodes (component pin connections) in this net
            node_matches = re.findall(
                r'\(node\s+\(ref\s+"([^"]+)"\)\s+\(pin\s+"([^"]+)"\)',
                part
            )
            
            for ref, pin in node_matches:
                nets[net_name]['nodes'].append((ref, pin))
                
                # Add to component's pin mapping
                if ref in components:
                    if 'pins' not in components[ref]:
                        components[ref]['pins'] = {}
                    components[ref]['pins'][pin] = spice_net
        
        return components, nets
    
    def clean_net_name(self, net_name):
        # Ground handling
        if net_name.upper() in ['GND', 'GROUND', 'VSS', '0']:
            return '0'

        # Remove leading slash
        cleaned = net_name.lstrip('/')

        # Replace ALL invalid characters with underscore
        cleaned = re.sub(r'[^a-zA-Z0-9]', '_', cleaned)

        # Collapse multiple underscores → one
        cleaned = re.sub(r'_+', '_', cleaned)

        # Remove leading/trailing underscores
        cleaned = cleaned.strip('_')

        # Limit length (important for ngspice stability)
        cleaned = cleaned[:20]

        # Ensure valid start
        if not cleaned or cleaned[0].isdigit():
            cleaned = 'N' + cleaned

        return cleaned
    
    def get_component_nodes(self, ref, components, nets):
        """
        Get the SPICE node names for a component's pins.
        Returns list of node names in pin order [pin1_node, pin2_node, ...]
        """
        nodes = []
        
        if ref not in components:
            return nodes
        
        comp_pins = components[ref].get('pins', {})
        
        # Sort pins numerically
        sorted_pins = sorted(comp_pins.keys(), 
                           key=lambda x: int(x) if x.isdigit() else 0)
        
        for pin in sorted_pins:
            nodes.append(comp_pins[pin])
        
        return nodes
    
    def component_to_spice(self, ref, comp_data, nets):
        """
        Convert a single component to its SPICE line.
        
        SPICE format:
        R1 node1 node2 10k          <- resistor
        C1 node+ node- 100nF        <- capacitor
        L1 node+ node- 1mH          <- inductor
        V1 node+ node- DC 5         <- DC voltage source
        Q1 collector base emitter BC547  <- BJT
        """
        if not ref:
            return None
        
        prefix = ref[0].upper()  # First letter: R, C, L, V, Q, M etc.
        value = comp_data.get('value', '?')
        pins = comp_data.get('pins', {})
        
        # Get nodes in pin order
        sorted_pins = sorted(pins.keys(), 
                           key=lambda x: int(x) if x.isdigit() else 0)
        nodes = [pins[p] for p in sorted_pins]
        
        # Need at least 2 nodes for most components
        while len(nodes) < 2:
            nodes.append('0')  # Pad with GND if missing
        
        if prefix == 'R':
            # Resistor: R<name> <node+> <node-> <value>
            return f"{ref} {nodes[0]} {nodes[1]} {value}"
        
        elif prefix == 'C':
            # Capacitor: C<name> <node+> <node-> <value>
            return f"{ref} {nodes[0]} {nodes[1]} {value}"
        
        elif prefix == 'L':
            # Inductor: L<name> <node+> <node-> <value>
            return f"{ref} {nodes[0]} {nodes[1]} {value}"
      
        elif prefix == 'V':
            sim_type = comp_data.get('sim_type', '')
            sim_params = comp_data.get('sim_params', '')
 
                
            if sim_type == 'SIN' and sim_params:
                params = {}
                for p in sim_params.split():
                    if '=' in p:
                        k, v = p.split('=')
                        params[k] = v
                dc = params.get('dc', '0')
                ampl = params.get('ampl', '1')
                freq = params.get('f', '1k')
                ac = params.get('ac', '1')
                # Include both AC and SIN so source works for both AC and transient
                return f"{ref} {nodes[0]} {nodes[1]} AC {ac} SIN({dc} {ampl} {freq})"
      
                
            
            elif sim_type == 'PULSE' and sim_params:
                # Parse pulse parameters
                params = {}
                for p in sim_params.split():
                    if '=' in p:
                        k, v = p.split('=')
                        params[k] = v
                v1 = params.get('v1', '0')
                v2 = params.get('v2', '5')
                td = params.get('td', '0')
                tr = params.get('tr', '1n')
                tf = params.get('tf', '1n')
                pw = params.get('pw', '5m')
                per = params.get('per', '10m')
                return f"{ref} {nodes[0]} {nodes[1]} PULSE({v1} {v2} {td} {tr} {tf} {pw} {per})"
                
            # Voltage source: V<name> <node+> <node-> DC <value>
            # Check if value already has AC/DC/PULSE specification
            elif any(kw in value.upper() for kw in ['DC', 'AC', 'PULSE', 'SIN']):
                return f"{ref} {nodes[0]} {nodes[1]} {value}"
            else:
                return f"{ref} {nodes[0]} {nodes[1]} DC {value}"
                
                
                
                
                
                
                
                
        
        elif prefix == 'I':
            # Current source
            return f"{ref} {nodes[0]} {nodes[1]} DC {value}"
        
        elif prefix == 'D':
            # Always use 'dled' — matches our auto-injected model below
            # Diode SPICE format: D<name> <anode> <kathode> <model>
            # KiCad LED symbol: pin1=Kathode, pin2=Anode
            # After numeric sort: nodes[0]=pin1=Kathode, nodes[1]=pin2=Anode
            # So swap them: anode first, then kathode
            anode = nodes[1] if len(nodes) > 1 else nodes[0]
            kathode = nodes[0]
            return f"{ref} {anode} {kathode} dled"
        
        elif prefix == 'Q':
            # BJT: Q<name> <collector> <base> <emitter> <model>
            while len(nodes) < 3:
                nodes.append('0')
            return f"{ref} {nodes[0]} {nodes[1]} {nodes[2]} {value}"
        
        elif prefix == 'M':
            # MOSFET: M<name> <drain> <gate> <source> <bulk> <model>
            while len(nodes) < 4:
                nodes.append('0')
            return f"{ref} {nodes[0]} {nodes[1]} {nodes[2]} {nodes[3]} {value}"
        
        elif prefix in ['U', 'X']:
            # IC subcircuit: X<name> <node1> <node2>... <subckt_name>
            node_str = ' '.join(nodes)
            return f"* UNSUPPORTED IC (needs .subckt model): {ref} {node_str} {value}"
        
        else:
            # Unknown component — add as comment
            node_str = ' '.join(nodes)
            return f"* UNKNOWN: {ref} {node_str} {value}"
    
    def get_analysis_command(self, analysis_type, params=None):
        """
        Generate the Ngspice analysis command.
        
        Types:
            tran: Transient analysis (time domain) - most common
            ac:   AC frequency sweep
            dc:   DC sweep
            op:   Operating point (no parameters needed)
        """
        if params is None:
            params = {}
        
        if analysis_type == 'tran':
            # .tran <step> <stop> [start] [max_step]
            start = params.get('start', '0')
            step = params.get('step', '1us')
            stop = params.get('stop', '10ms')
            return f".tran {step} {stop} {start}"
        
        elif analysis_type == 'ac':
            # .ac <type> <points> <fstart> <fstop>
            scale = params.get('scale', 'dec')
            points = params.get('points', '100')
            fstart = params.get('fstart', '1Hz')
            fstop = params.get('fstop', '1MEGHz')
            return f".ac {scale} {points} {fstart} {fstop}"
        
        elif analysis_type == 'dc':
            # .dc <source> <start> <stop> <step>
            source = params.get('source', 'V1')
            start = params.get('start', '0')
            stop = params.get('stop', '5')
            step = params.get('step', '0.1')
            return f".dc {source} {start} {stop} {step}"
        
        elif analysis_type == 'op':
            return ".op"
        
        else:
            return ".tran 1us 10ms"  # Default
    
    def get_output_commands(self, nets, analysis_type):
        """
        Generate .print and .probe commands to output simulation results.
        """
        commands = []
        
        # Get all non-ground net names
        output_nets = [
            data['spice_name'] 
            for name, data in nets.items()
            if data['spice_name'] != '0'
        ]
        
        if not output_nets:
            return [".probe v(*)"]
        
        if analysis_type == 'tran':
            # Print voltage at every node over time
            for net in output_nets[:5]:  # Limit to first 5 to keep it manageable
                commands.append(f".print tran v({net})")
        
        elif analysis_type == 'ac':
            for net in output_nets[:5]:
                commands.append(f".print ac v({net})")
        
        elif analysis_type == 'dc':
            for net in output_nets[:5]:
                commands.append(f".print dc v({net})")
        
        # Also add .probe for waveform viewer
        commands.append(".probe v(*)")
        
        return commands



# Add this class to your esim_bridge.py file
# Add it ABOVE the ESimBridgePlugin class

class AnalysisConfigDialog(wx.Dialog):
    """
    Dialog box that appears when user clicks 'Simulate in eSim'.
    
    Lets user choose:
    - Analysis type (Transient, AC, DC, Operating Point)
    - Analysis parameters (time range, frequency range, etc.)
    """
    
    def __init__(self, parent):
        super().__init__(
            parent,
            title="eSim Simulation Bridge",
            size=(500, 400),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        
        self.analysis_type = 'tran'  # Default
        self.analysis_params = {}
        
        self._build_ui()
        self.Centre()  # Center the dialog on screen
    
    def _build_ui(self):
        """Build the dialog user interface"""
        
        # Main vertical layout
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # ── Title ───────────────────────────────────────
        title = wx.StaticText(self, label="eSim One-Click Simulation Bridge")
        title_font = wx.Font(12, wx.FONTFAMILY_DEFAULT, 
                            wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)
        main_sizer.Add(title, 0, wx.ALL | wx.EXPAND, 10)
        
        # Divider line
        line = wx.StaticLine(self)
        main_sizer.Add(line, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # ── Analysis Type Selection ──────────────────────
        type_label = wx.StaticText(self, label="Simulation Type:")
        main_sizer.Add(type_label, 0, wx.ALL, 10)
        
        self.type_choices = wx.RadioBox(
            self,
            label="",
            choices=[
                "Transient Analysis (.tran) — Output vs Time",
                "AC Analysis (.ac) — Output vs Frequency",
                "DC Analysis (.dc) — Output vs DC voltage",
                "Operating Point (.op) — Single DC point"
            ],
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS
        )
        self.type_choices.SetSelection(0)  # Default: Transient
        self.type_choices.Bind(wx.EVT_RADIOBOX, self._on_type_change)
        main_sizer.Add(self.type_choices, 0, wx.ALL | wx.EXPAND, 10)
        
        # ── Parameters Panel ────────────────────────────
        self.params_panel = wx.Panel(self)
        self.params_sizer = wx.FlexGridSizer(rows=4, cols=2, vgap=5, hgap=10)
        self.params_sizer.AddGrowableCol(1)
        
        self._build_tran_params()  # Show transient params by default
        
        self.params_panel.SetSizer(self.params_sizer)
        main_sizer.Add(self.params_panel, 0, wx.ALL | wx.EXPAND, 10)
        
        # ── Buttons ──────────────────────────────────────
        btn_sizer = wx.StdDialogButtonSizer()
        
        self.run_btn = wx.Button(self, wx.ID_OK, "Simulate in eSim →")
        self.run_btn.SetDefault()  # Pressing Enter clicks this button
        cancel_btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        
        btn_sizer.AddButton(self.run_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        
        self.SetSizer(main_sizer)
        self.Fit()
    
    def _build_tran_params(self):
        """Build parameter inputs for Transient analysis"""
        self.params_sizer.Clear(True)
        
        # Start time
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="Start Time:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.start_input = wx.TextCtrl(self.params_panel, value="0")
        self.params_sizer.Add(self.start_input, 1, wx.EXPAND)
        
        # Step size
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="Step Time:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.step_input = wx.TextCtrl(self.params_panel, value="1us")
        self.params_sizer.Add(self.step_input, 1, wx.EXPAND)
        
        # Stop time
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="Stop Time:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.stop_input = wx.TextCtrl(self.params_panel, value="10ms")
        self.params_sizer.Add(self.stop_input, 1, wx.EXPAND)
        
        # Help text
        help_text = wx.StaticText(
            self.params_panel,
            label="Tip: Use units like us, ms, ns, s"
        )
        help_text.SetForegroundColour(wx.Colour(100, 100, 100))
        self.params_sizer.Add(help_text, 0, wx.ALL)
        
        self.params_panel.Layout()
    
    def _build_ac_params(self):
        """Build parameter inputs for AC analysis"""
        self.params_sizer.Clear(True)
        
        # Scale
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="Scale:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.scale_input = wx.Choice(self.params_panel, choices=["dec", "lin", "oct"])
        self.scale_input.SetSelection(0)  # Default: dec
        self.params_sizer.Add(self.scale_input, 1, wx.EXPAND)
        
        # Start Frequency
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="Start Frequency:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.fstart_input = wx.TextCtrl(self.params_panel, value="1Hz")
        self.params_sizer.Add(self.fstart_input, 1, wx.EXPAND)
        
        # Stop Frequency
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="Stop Frequency:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.fstop_input = wx.TextCtrl(self.params_panel, value="1MEGHz")
        self.params_sizer.Add(self.fstop_input, 1, wx.EXPAND)
        
        # No. of Points
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="No. of Points:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.points_input = wx.TextCtrl(self.params_panel, value="100")
        self.params_sizer.Add(self.points_input, 1, wx.EXPAND)
        
        self.params_panel.Layout()
    
    def _build_dc_params(self):
        """Build parameter inputs for DC sweep"""
        self.params_sizer.Clear(True)
        
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="Source Name:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.source_input = wx.TextCtrl(self.params_panel, value="V1")
        self.params_sizer.Add(self.source_input, 1, wx.EXPAND)
        
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="Start Value:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.dc_start_input = wx.TextCtrl(self.params_panel, value="0")
        self.params_sizer.Add(self.dc_start_input, 1, wx.EXPAND)
        
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="Stop Value:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.dc_stop_input = wx.TextCtrl(self.params_panel, value="5")
        self.params_sizer.Add(self.dc_stop_input, 1, wx.EXPAND)
        
        self.params_sizer.Add(
            wx.StaticText(self.params_panel, label="Step:"),
            0, wx.ALIGN_CENTER_VERTICAL
        )
        self.dc_step_input = wx.TextCtrl(self.params_panel, value="0.1")
        self.params_sizer.Add(self.dc_step_input, 1, wx.EXPAND)
        
        self.params_panel.Layout()
    
    def _on_type_change(self, event):
        """Called when user selects a different analysis type"""
        selection = self.type_choices.GetSelection()
        
        if selection == 0:
            self.analysis_type = 'tran'
            self._build_tran_params()
        elif selection == 1:
            self.analysis_type = 'ac'
            self._build_ac_params()
        elif selection == 2:
            self.analysis_type = 'dc'
            self._build_dc_params()
        elif selection == 3:
            self.analysis_type = 'op'
            self.params_sizer.Clear(True)
            self.params_panel.Layout()
        
        self.Fit()
    
    def get_analysis_type(self):
        """Return selected analysis type string"""
        return self.analysis_type
    
    def get_analysis_params(self):
        """Return dict of parameters based on selected analysis type"""
        params = {}
        
        try:
            if self.analysis_type == 'tran':
                params['start'] = self.start_input.GetValue()
                params['step'] = self.step_input.GetValue()
                params['stop'] = self.stop_input.GetValue()
            
            elif self.analysis_type == 'ac':
                params['scale'] = self.scale_input.GetStringSelection()
                params['fstart'] = self.fstart_input.GetValue()
                params['fstop'] = self.fstop_input.GetValue()
                params['points'] = self.points_input.GetValue()
            
            elif self.analysis_type == 'dc':
                params['source'] = self.source_input.GetValue()
                params['start'] = self.dc_start_input.GetValue()
                params['stop'] = self.dc_stop_input.GetValue()
                params['step'] = self.dc_step_input.GetValue()
        
        except AttributeError:
            pass  # Input field doesn't exist for current type
        
        return params



class ESimLauncher:
    """
    Finds and launches eSim with a pre-loaded netlist.
    Updated for eSim 2.5 installed via native Ubuntu installer.
    """
    
    # Your specific eSim paths (discovered during installation)
    ESIM_SCRIPT = os.path.expanduser(
        '~/Downloads/eSim-2.5/src/frontEnd/Application.py'
    )
    ESIM_PYTHON = os.path.expanduser('~/.esim/env/bin/python3')
    ESIM_SRC    = os.path.expanduser('~/Downloads/eSim-2.5/src')
    ESIM_DIR    = os.path.expanduser('~/Downloads/eSim-2.5/src/frontEnd')

    def find_esim(self):
        """
        Check if eSim is available on this system.
        Returns True if found, False if not.
        """
        return (
            os.path.exists(self.ESIM_SCRIPT) and
            os.path.exists(self.ESIM_PYTHON)
        )

    def launch(self, netlist_path):
        """
        Launch eSim with the given netlist file.
        Returns (success: bool, message: str)
        """
        import time

        # ── Check eSim is installed ─────────────────────
        if not self.find_esim():
            return False, (
                "eSim not found.\n\n"
                "Expected at:\n"
                f"{self.ESIM_SCRIPT}\n\n"
                "Please install eSim 2.5 from:\n"
                "https://static.fossee.in/esim/installation-files/eSim-2.5.zip\n\n"
                f"Your SPICE file has been saved to:\n{netlist_path}\n"
                "You can open it manually once eSim is installed."
            )

        # ── Copy netlist to home dir ────────────────────
        # eSim must be launched from its own directory,
        # so we save the netlist to home directory to keep
        # the path simple and accessible
        home_netlist = os.path.expanduser('~/esim_bridge_simulation.cir')
        try:
            import shutil
            shutil.copy2(netlist_path, home_netlist)
        except Exception as e:
            # If copy fails, use original path
            home_netlist = netlist_path

        try:
            # ── Build environment ───────────────────────
            import os as os_module
            env = os_module.environ.copy()
            env['PYTHONPATH'] = self.ESIM_SRC

            # ── Build launch command ────────────────────
            # Must run from ESIM_DIR for relative paths to work
            cmd = [self.ESIM_PYTHON, 'Application.py']

            # ── Launch as separate process ──────────────
            process = subprocess.Popen(
                cmd,
                cwd=self.ESIM_DIR,   # CRITICAL: run from frontEnd/ dir
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Wait 3 seconds to check it started
            time.sleep(3)

            if process.poll() is None:
                # Still running — success
                return True, (
                    f"eSim launched successfully!\n"
                    f"PID: {process.pid}\n\n"
                    f"Your SPICE file is at:\n{home_netlist}\n\n"
                    f"In eSim:\n"
                    f"1. Create/open a project\n"
                    f"2. Click 'Convert KiCad to Ngspice'\n"
                    f"3. Browse to: {home_netlist}"
                )
            else:
                stdout, stderr = process.communicate()
                return False, (
                    f"eSim failed to start.\n\n"
                    f"Error:\n{stderr.decode()[:500]}"
                )

        except FileNotFoundError:
            return False, (
                f"Could not find Python executable:\n{self.ESIM_PYTHON}\n\n"
                "Make sure eSim virtual environment is intact."
            )
        except Exception as e:
            return False, f"Unexpected error launching eSim:\n{str(e)}"




class PreflightChecker:
    """
    Checks everything is ready before attempting simulation.
    Gives user clear, friendly error messages.
    """
    
    def run_all_checks(self, schematic_path):
        """
        Run all preflight checks.
        Returns list of (type, message) tuples.
        type is 'error', 'warning', or 'ok'
        """
        results = []
        
        # Check 1: Schematic file exists
        if not os.path.exists(schematic_path):
            results.append(('error', 
                f"Schematic file not found:\n{schematic_path}"))
            return results  # Can't continue without schematic
        
        results.append(('ok', f"Schematic found: {schematic_path}"))
        
        # Check 2: kicad-cli is available
        try:
            result = subprocess.run(
                ['kicad-cli', '--version'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                results.append(('ok', 
                    f"kicad-cli available: {result.stdout.strip()}"))
            else:
                results.append(('error', 
                    "kicad-cli not working correctly"))
        except FileNotFoundError:
            results.append(('error', 
                "kicad-cli not found. Is KiCad 9 installed correctly?"))
        
        # Check 3: eSim is installed
        launcher = ESimLauncher()
        esim_path = launcher.find_esim()
        if esim_path:
            results.append(('ok', f"eSim found: {esim_path}"))
        else:
            results.append(('warning', 
                "eSim not found. SPICE file will be saved but eSim "
                "won't auto-launch. You can open the .cir file manually."))
        
        # Check 4: Write permissions for temp directory
        try:
            test_file = '/tmp/esim_bridge_test.tmp'
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            results.append(('ok', "Write access to /tmp confirmed"))
        except:
            results.append(('error', 
                "Cannot write to /tmp directory. "
                "Check permissions."))
        
        return results
    
    def show_results_dialog(self, results):
        """
        Show preflight check results to user.
        Returns True if user wants to continue, False if they want to cancel.
        """
        errors = [r for r in results if r[0] == 'error']
        warnings = [r for r in results if r[0] == 'warning']
        oks = [r for r in results if r[0] == 'ok']
        
        if not errors and not warnings:
            # All good — no need to show dialog
            return True
        
        # Build message
        message = ""
        
        if errors:
            message += "ERRORS (must fix before simulating):\n"
            for _, msg in errors:
                message += f"  ✗ {msg}\n"
            message += "\n"
        
        if warnings:
            message += "WARNINGS (simulation may still work):\n"
            for _, msg in warnings:
                message += f"  ⚠ {msg}\n"
            message += "\n"
        
        if oks:
            message += "OK:\n"
            for _, msg in oks:
                message += f"  ✓ {msg}\n"
        
        if errors:
            wx.MessageBox(
                message,
                "eSim Bridge — Preflight Check Failed",
                wx.OK | wx.ICON_ERROR
            )
            return False
        else:
            # Only warnings — ask user if they want to continue
            result = wx.MessageBox(
                message + "\nContinue anyway?",
                "eSim Bridge — Preflight Warnings",
                wx.YES_NO | wx.ICON_WARNING
            )
            return result == wx.YES




class SimulationReadyDialog(wx.Dialog):
    """
    Shows after successful conversion, before launching eSim.
    Shows what was converted and gives options.
    """
    
    def __init__(self, parent, spice_path, components, analysis_type, params):
        super().__init__(parent, title="Ready to Simulate",
                        size=(550, 450))
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Success header
        header = wx.StaticText(self, 
            label="✓ Schematic converted successfully!")
        header.SetForegroundColour(wx.Colour(0, 128, 0))
        font = wx.Font(11, wx.FONTFAMILY_DEFAULT, 
                      wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        header.SetFont(font)
        sizer.Add(header, 0, wx.ALL, 10)
        
        # Summary
        summary = (
            f"Components converted: {len(components)}\n"
            f"Analysis type: {analysis_type.upper()}\n"
            f"SPICE file: {spice_path}\n"
        )
        if params:
            summary += f"Parameters: {params}"
        
        summary_text = wx.StaticText(self, label=summary)
        sizer.Add(summary_text, 0, wx.ALL, 10)
        
        # SPICE file preview
        preview_label = wx.StaticText(self, label="Generated SPICE file:")
        sizer.Add(preview_label, 0, wx.LEFT | wx.TOP, 10)
        
        try:
            with open(spice_path, 'r') as f:
                spice_content = f.read()
        except:
            spice_content = "Could not read file"
        
        preview = wx.TextCtrl(
            self, value=spice_content,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=(-1, 150)
        )
        preview.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE,
                               wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        sizer.Add(preview, 1, wx.ALL | wx.EXPAND, 10)
        
        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        launch_btn = wx.Button(self, wx.ID_OK, "Launch eSim →")
        launch_btn.SetDefault()
        
        open_file_btn = wx.Button(self, wx.ID_ANY, "Open .cir File")
        open_file_btn.Bind(wx.EVT_BUTTON, 
            lambda e: os.system(f'xdg-open {spice_path}'))
        
        cancel_btn = wx.Button(self, wx.ID_CANCEL, "Close")
        
        btn_sizer.Add(launch_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(open_file_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(cancel_btn, 0)
        
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizer(sizer)





class ESimBridgePlugin(pcbnew.ActionPlugin):
    
    def defaults(self):
        self.name = "eSim Simulation Bridge"
        self.category = "eSim Tools"
        self.description = "Launch eSim simulation with one click"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(
            os.path.dirname(__file__), 'icon.png'
        )
    def Run(self):
        """Main function — called when user clicks the plugin button"""
        

        # Set up logging to a file
        LOG_FILE = os.path.expanduser("~/.local/share/kicad/esim_bridge.log")

        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger('ESimBridge')
        logger.info("Plugin Run() called")
        
        
        
        # Delete stale .raw file immediately to prevent UTF-8 error
        workspace = os.path.expanduser("~/eSim-Workspace")
        project_name = "esim_bridge_project"
        project_folder = os.path.join(workspace, project_name)
        raw_file = os.path.join(project_folder, project_name + ".raw")
        try:
            if os.path.exists(raw_file):
                os.remove(raw_file)
        except Exception:
            pass
        
        


        # ── Step 1: Show analysis config dialog ──────────────
        app = wx.App.Get()
        if not app:
            app = wx.App()
        
        dialog = AnalysisConfigDialog(None)
        
        if dialog.ShowModal() != wx.ID_OK:
            dialog.Destroy()
            return  # User clicked Cancel
        
        analysis_type = dialog.get_analysis_type()
        analysis_params = dialog.get_analysis_params()
        dialog.Destroy()
        
        # ── Step 2: Get schematic path ────────────────────────
        schematic_path = self.get_schematic_path()
        
        if not schematic_path:
            wx.MessageBox(
                "No schematic found.\nPlease open a schematic first.",
                "eSim Bridge",
                wx.OK | wx.ICON_ERROR
            )
            return
            
        # ── Step 2: Run preflight checks ──────────────────────
        checker = PreflightChecker()
        check_results = checker.run_all_checks(schematic_path)
        if not checker.show_results_dialog(check_results):
            return  # User cancelled or errors found
        
        # ── Step 3: Export netlist ────────────────────────────
        netlist_xml_path = "/tmp/esim_bridge_netlist.net"
        
        progress = wx.ProgressDialog(
            "eSim Bridge",
            "Step 1/3: Exporting netlist from KiCad...",
            maximum=3,
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE
        )
        
        success = self.export_netlist(schematic_path, netlist_xml_path)
        
        if not success:
            progress.Destroy()
            wx.MessageBox(
                "Failed to export netlist.\n"
                "Make sure kicad-cli is available.",
                "eSim Bridge Error",
                wx.OK | wx.ICON_ERROR
            )
            return
        
        # ── Step 4: Convert to SPICE format ──────────────────
        progress.Update(1, "Step 2/3: Converting to SPICE format...")
        
        spice_output_path = "/tmp/esim_bridge_simulation.cir"
        
        converter = SPICEConverter()
        success = converter.convert(
            netlist_path=netlist_xml_path,
            output_path=spice_output_path,
            analysis_type=analysis_type,
            analysis_params=analysis_params
        )
        
        if not success:
            progress.Destroy()
            wx.MessageBox(
                "Failed to convert netlist to SPICE format.",
                "eSim Bridge Error",
                wx.OK | wx.ICON_ERROR
            )
            return
        
        # ── Step 5: Launch eSim ───────────────────────────────
        progress.Update(2, "Step 3/3: Launching eSim...")
        

        import shutil

        workspace = os.path.expanduser("~/eSim-Workspace")
        project_name = "esim_bridge_project"
        project_folder = os.path.join(workspace, project_name)

        # Create project folder inside eSim workspace
        os.makedirs(project_folder, exist_ok=True)
        
        # Create images folder (required for data row display)
        os.makedirs(os.path.join(project_folder, "images"), exist_ok=True)

        
        # Use SPICEConverter output (pure SPICE) as .cir.out
        with open(spice_output_path, 'r') as f:
            spice_content = f.read()

        # Remove .end and append eSim control block
        spice_content = spice_content.replace('.end\n', '').strip() + "\n"
        spice_content += "* Control Statements\n"
        spice_content += ".control\n"
        spice_content += "run\n"
        if analysis_type == 'tran':
            spice_content += "print allv\n"
            spice_content += "print alli\n"
            spice_content += "print allv > plot_data_v.txt\n"
            spice_content += "print alli > plot_data_i.txt\n"
        elif analysis_type == 'ac':
            spice_content += "print allv\n"
            spice_content += "print alli\n"
            spice_content += "print allv > plot_data_v.txt\n"
            spice_content += "print alli > plot_data_i.txt\n"
        else:
            spice_content += "print allv\n"
            spice_content += "print alli\n"
            spice_content += "print allv > plot_data_v.txt\n"
            spice_content += "print alli > plot_data_i.txt\n"
        spice_content += ".endc\n"
        spice_content += ".end\n"


        # Delete stale .raw file before writing new simulation files
        raw_file_pre = os.path.join(project_folder, project_name + ".raw")
        try:
            if os.path.exists(raw_file_pre):
                os.remove(raw_file_pre)
        except Exception:
            pass

        # Write to .cir.out
        dest = os.path.join(project_folder, project_name + ".cir.out")
        with open(dest, 'w') as f:
            f.write(spice_content)

        # Also copy netlist as .cir
        cir_dest = os.path.join(project_folder, project_name + ".cir")
        shutil.copy(spice_output_path, cir_dest)
                
        
        
        
        
        
        
        
        # Create .proj file (eSim requires this to recognize the folder as a project)
        proj_file = os.path.join(project_folder, project_name + ".proj")
        open(proj_file, 'w').close()
        
        
        
        # Write analysis file — eSim uses this to determine plot type
        analysis_file = os.path.join(project_folder, "analysis")
        if analysis_type == 'ac':
            scale = analysis_params.get('scale', 'dec')
            fstart = analysis_params.get('fstart', '1Hz')
            fstop = analysis_params.get('fstop', '1MEGHz')
            points = analysis_params.get('points', '100')
            analysis_content = f".ac {scale} {points} {fstart} {fstop}"
        elif analysis_type == 'tran':
            start = analysis_params.get('start', '0')
            step = analysis_params.get('step', '1us')
            stop = analysis_params.get('stop', '10ms')
            analysis_content = f".tran {step} {stop} {start}"
        elif analysis_type == 'dc':
            source = analysis_params.get('source', 'V1')
            start = analysis_params.get('start', '0')
            stop = analysis_params.get('stop', '5')
            step = analysis_params.get('step', '0.1')
            analysis_content = f".dc {source} {start} {stop} {step}"
        else:
            analysis_content = ".op"
        with open(analysis_file, 'w') as f:
            f.write(analysis_content)
        
        

        progress.Destroy()
        
        
        # Show results dialog before launching eSim
        converter_temp = SPICEConverter()
        components_temp, _ = converter_temp.parse_full_netlist(netlist_xml_path)
        
        
        
        # For OP analysis, skip eSim launch — just show results

        if analysis_type == 'op':
            # Run ngspice directly to get OP results
            try:
                env = os.environ.copy()
                env['PYTHONPATH'] = '/home/imran-farhat/Downloads/eSim-2.5/src'
                result = subprocess.run(
                    ['ngspice', '-b', dest],
                    capture_output=True, text=True, timeout=10,
                    cwd=project_folder, env=env
                )
                output = result.stdout + result.stderr
                # Extract the node voltage lines
                lines = [l.strip() for l in output.split('\n') 
                         if '=' in l and ('net_' in l.lower() or 'v(' in l.lower()
                         or any(c.isdigit() for c in l))]
                values = '\n'.join(lines) if lines else output[:500]
            except Exception as e:
                values = f"Could not get values: {e}"
            
            wx.MessageBox(
                f"Operating Point Analysis completed!\n\n"
                f"DC Node Voltages:\n{values}\n\n"
                "Note: OP analysis does not produce a waveform graph.",
                "eSim Bridge — OP Analysis",
                wx.OK | wx.ICON_INFORMATION
            )
            return
        

        results_dialog = SimulationReadyDialog(
            None,
            spice_output_path,
            components_temp,
            analysis_type,
            analysis_params
        )

        if results_dialog.ShowModal() != wx.ID_OK:
            results_dialog.Destroy()
            return

        results_dialog.Destroy()
        
        
        
        # Delete stale .raw file to prevent UTF-8 error on next eSim open
        raw_file = os.path.join(project_folder, project_name + ".raw")
        try:
            if os.path.exists(raw_file):
                os.remove(raw_file)
        except Exception:
            pass
                
        

        # Launch eSim
        env = os.environ.copy()
        env['PYTHONPATH'] = '/home/imran-farhat/Downloads/eSim-2.5/src'

        subprocess.Popen(
            ['/home/imran-farhat/.esim/env/bin/python3', 'Application.py'],
            cwd='/home/imran-farhat/Downloads/eSim-2.5/src/frontEnd',
            env=env
        )

        wx.MessageBox(
            "eSim launched successfully!\n\n"
            "Your project is ready. Inside eSim:\n"
            "1. Double-click 'esim_bridge_project' in the project tree\n"
            "2. Click 'Simulate'\n"
            "3. Click 'Plot' to see the graph",
            "eSim Bridge — Success!",
            wx.OK | wx.ICON_INFORMATION
        )
    
    
    def get_schematic_path(self):
        """
        Find the path of the currently open schematic.
        KiCad stores this in the board/schematic object.
        """
        try:
            # Try to get path from pcbnew API
            board = pcbnew.GetBoard()
            if board:
                project_path = board.GetFileName()
                if project_path:
                    # Convert .kicad_pcb path to .kicad_sch path
                    sch_path = project_path.replace(
                        '.kicad_pcb', '.kicad_sch'
                    )
                    if os.path.exists(sch_path):
                        return sch_path
        except:
            pass
        
        # Fallback: ask user to select the file
        dialog = wx.FileDialog(
            None,
            "Select KiCad Schematic File",
            wildcard="KiCad Schematic (*.kicad_sch)|*.kicad_sch",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        )
        
        if dialog.ShowModal() == wx.ID_OK:
            return dialog.GetPath()
        
        return None
    
    def export_netlist(self, schematic_path, output_path):
        """
        Use kicad-cli to export the netlist from the schematic.
        This is the most reliable way to get netlist data.
        
        Returns True if successful, False if failed.
        """
        try:
            # kicad-cli command to export netlist
            command = [
                'kicad-cli',
                'sch',
                'export',
                'netlist',
                '--output', output_path,
                '--format', 'kicadsexpr',  # S-expression format
                schematic_path
            ]
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            if result.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                print(f"kicad-cli error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("Error: kicad-cli timed out")
            return False
        except FileNotFoundError:
            print("Error: kicad-cli not found")
            return False
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def parse_netlist_components(self, netlist_path):
        """
        Parse the KiCad netlist file and extract all components.
        
        Returns a dictionary: {reference: value}
        Example: {"R1": "10k", "C1": "100nF", "U1": "LM741"}
        """
        components = {}
        
        try:
            with open(netlist_path, 'r') as f:
                content = f.read()
            
            # Find all component blocks using regex
            # Pattern matches: (comp (ref "R1") ... (value "10k") ...)
            comp_pattern = r'\(comp\s+\(ref\s+"([^"]+)"\)[^)]*\(value\s+"([^"]+)"\)'
            matches = re.findall(comp_pattern, content, re.DOTALL)
            
            for ref, value in matches:
                components[ref] = value
                
        except Exception as e:
            print(f"Error parsing netlist: {e}")
        
        return components

# Register plugin with KiCad
ESimBridgePlugin().register()
