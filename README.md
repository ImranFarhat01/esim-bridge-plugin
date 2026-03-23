![Platform](https://img.shields.io/badge/platform-linux-blue)
![KiCad](https://img.shields.io/badge/KiCad-8%2F9-green)
![License](https://img.shields.io/badge/license-GPL--3.0-orange)
# eSim One-Click Simulation Bridge (P-BRIDGE)

A KiCad 8.0 / 9.0 plugin that bridges KiCad schematics directly to eSim 2.5 simulation with a single click.

**Developed for:** FOSSEE Semester Long Internship Spring 2026 — Task 6: KiCad Plugin Development  
**Author:** Imran Farhat  
**Institution:** IIT Bombay (FOSSEE)

---

## What It Does

Eliminates the manual workflow of exporting netlists, converting to SPICE, and setting up eSim projects. One click does everything:

1. Exports KiCad schematic netlist automatically
2. Converts it to SPICE format
3. Sets up the eSim project folder
4. Launches eSim with simulation ready to run
5. Automatically generates .cir.out with ngspice control block
6. Automatically exports voltage and current data (plot_data_v.txt, plot_data_i.txt)
7. Runs Operating Point analysis internally using ngspice

---

## Requirements

- **OS:** Ubuntu 20.04 / 22.04 / 24.04 (Linux)
- **KiCad:** 8.0 (with `kicad-cli` available)
- **eSim:** 2.5 (installed at `~/Downloads/eSim-2.5/`)
- **Python:** 3.10+
- **ngspice:** installed (comes with eSim)

Important:
The plugin expects eSim to be installed at:

~/Downloads/eSim-2.5/

If installed elsewhere, update paths inside esim_bridge.py.

---

## Installation

### Step 1: Clone the repository

```bash
git clone https://github.com/ImranFarhat01/esim-bridge-plugin.git
```

### Step 2: Copy plugin folder to KiCad

```bash
cp -r esim-bridge-plugin/esim_bridge ~/.local/share/kicad/<version>/scripting/plugins/
Note: Replace <version> with your KiCad version (e.g., 8.0 or 9.0)
```

That's it — no manual folder creation needed.

### Step 3: Verify installation

```bash
ls ~/.local/share/kicad/8.0/scripting/plugins/esim_bridge/
```

You should see: `esim_bridge.py`, `icon.png`, `__init__.py`

### Step 4: Restart KiCad

Close and reopen KiCad. The eSim Bridge icon will appear in the PCB Editor toolbar.

---

## How to Use

### 1. Open your schematic in KiCad Schematic Editor

Draw your circuit with proper simulation models set on voltage/current sources.

### 2. Open PCB Editor and click the eSim Bridge plugin button
(The plugin button appears in PCB Editor, not in schematic editor)

The plugin icon appears in the KiCad PCB Editor toolbar.

### 3. Select analysis type and parameters

| Analysis | Parameters |
|----------|-----------|
| Transient | Start Time, Step Time, Stop Time |
| AC | Scale (dec/lin/oct), Start Freq, Stop Freq, No. of Points |
| DC Sweep | Source Name, Start, Stop, Step |
| Operating Point | No parameters needed |

### 4. Click "Simulate in eSim →"

The plugin will:
- Export your netlist
- Convert to SPICE
- Write project files to `~/eSim-Workspace/esim_bridge_project/`
- Launch eSim automatically

### 5. In eSim

- Double-click `esim_bridge_project` in the project tree
- Click **Simulate**
- Click **Plot** to see the graph

---

## Supported Components

| KiCad Prefix | Component | SPICE Format |
|---|---|---|
| R | Resistor | `R1 node1 node2 10k` |
| C | Capacitor | `C1 node1 node2 100nF` |
| L | Inductor | `L1 node1 node2 1mH` |
| V (VSIN) | Sine voltage source | `V1 n+ n- AC 1 SIN(0 1 1k)` |
| V (PULSE) | Pulse voltage source | `V1 n+ n- PULSE(0 5 0 1n 1n 5m 10m)` |
| V (DC) | DC voltage source | `V1 n+ n- DC 5` |
| I | Current source | `I1 n+ n- DC 1m` |
| D | Diode | `D1 anode cathode model` |
| Q | BJT Transistor | `Q1 c b e model` |
| M | MOSFET | `M1 d g s b model` |
| U/X | IC Subcircuit | `X1 nodes subckt_name` |

---

## Supported Analysis Types

### Transient Analysis (.tran)
Simulates circuit behavior over time.
```
.tran <step> <stop> <start>
Example: .tran 1us 10ms 0
```

### AC Analysis (.ac)
Frequency response analysis.
```
.ac <dec/lin/oct> <points> <fstart> <fstop>
Example: .ac dec 100 1Hz 1MEGHz
```

### DC Sweep (.dc)
DC operating point vs voltage sweep.
```
.dc <source> <start> <stop> <step>
Example: .dc V1 0 5 0.1
```

### Operating Point (.op)
Single DC bias point calculation. Results shown directly in a message box.
Operating Point analysis is executed internally using ngspice.
eSim is not launched. Node voltages are shown in a message box.

---

## File Structure

```
esim_bridge/
├── esim_bridge.py      # Main plugin code
├── icon.png            # Plugin toolbar icon
├── __init__.py         # Package entry point
└── README.md           # This file
```

**Generated project files** (in `~/eSim-Workspace/esim_bridge_project/`):
```
esim_bridge_project/
├── esim_bridge_project.cir       # SPICE netlist
├── esim_bridge_project.cir.out   # SPICE with control block
├── esim_bridge_project.proj      # eSim project marker
├── analysis                      # Analysis type file
├── plot_data_v.txt               # Voltage simulation data
├── plot_data_i.txt               # Current simulation data
└── images/                       # Required by eSim
```

---

## Useful Terminal Commands

### View generated SPICE netlist
```bash
cat ~/eSim-Workspace/esim_bridge_project/esim_bridge_project.cir.out
```

### Verify analysis file
```bash
cat ~/eSim-Workspace/esim_bridge_project/analysis
```

### Check simulation output data
```bash
head -10 ~/eSim-Workspace/esim_bridge_project/plot_data_v.txt
```

### Count data points
```bash
wc -l ~/eSim-Workspace/esim_bridge_project/plot_data_v.txt
```

### Run simulation manually in ngspice
```bash
ngspice -b ~/eSim-Workspace/esim_bridge_project/esim_bridge_project.cir.out
```

### View plugin log
```bash
cat ~/.local/share/kicad/esim_bridge.log
```

---

## Known Limitations

1. **Operating Point (.op) graph:** eSim 2.5 does not support plotting OP results graphically. The plugin shows DC node voltages in a message box instead.

2. **UTF-8 error in terminal:** A benign `Error: UTF-8 syntax error` may appear in the ngspice terminal when eSim opens a second time. This does not affect simulation results.

3. **Auto project load:** eSim 2.5 requires manually double-clicking the project in the project tree. Auto-loading via command line is not supported by eSim's API.

4. **Linux only:** This plugin is designed and tested for Ubuntu Linux with eSim 2.5.

---

## Metadata

```json
{
    "name": "eSim Simulation Bridge",
    "identifier": "com.fossee.esim-bridge",
    "version": "1.0.0",
    "kicad_version": "8.0",
    "license": "GPL-3.0",
    "author": "Imran Farhat - FOSSEE Intern @ IIT Bombay", 
    "Email": "imranfarhat.official@gmail.com",  
    "FOSSEE Contact": "contact-esim@fossee.in"
}
```

---

## License

GPL-3.0 — Free to use, modify, and distribute with attribution.
