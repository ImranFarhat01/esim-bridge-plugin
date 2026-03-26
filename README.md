![Platform](https://img.shields.io/badge/platform-linux-blue)
![KiCad](https://img.shields.io/badge/KiCad-8%2F9-green)
![License](https://img.shields.io/badge/license-GPL--3.0-orange)

# eSim One-Click Simulation Bridge (P-BRIDGE)

A KiCad 8.0 / 9.0 plugin that bridges KiCad schematics directly to eSim 2.5 simulation with a single click.

**Developed for:** FOSSEE Semester Long Internship Spring 2026 - Task 6: KiCad Plugin Development  
**Author:** Imran Farhat  
**Institution:** IIT Bombay (FOSSEE)

---

## What It Does

Eliminates the manual workflow of exporting netlists, converting to SPICE, and setting up eSim projects. One click does everything:

1. Exports KiCad schematic netlist automatically using `kicad-cli`
2. Converts it to valid SPICE format with correct net names
3. Writes all required eSim project files automatically
4. Launches eSim with the project ready to simulate
5. Automatically generates `.cir.out` with ngspice control block
6. Exports voltage and current data (`plot_data_v.txt`, `plot_data_i.txt`)
7. Runs Operating Point analysis internally using ngspice (no eSim launch needed)

**Reduces the 10-15-step manual process to 4 steps in 30 seconds.**

---

## System Requirements

| Software | Version | Notes |
|---|---|---|
| Ubuntu Linux | 24.04 LTS | Tested on 24.04 |
| KiCad | 8.0 | Must include `kicad-cli` |
| eSim | 2.5 | Must be installed at `~/Downloads/eSim-2.5/` |
| ngspice | 35+ | Bundled with eSim |
| Python | 3.10+ | Comes with Ubuntu |
| git | Any | For cloning this repo |

### Supported Environments

| Environment | Status |
|---|---|
| Ubuntu 24.04 in VirtualBox (Windows host) | ✅ Fully tested - recommended |
| Native Ubuntu 24.04 Linux | ✅ Works perfectly |
| WSL 2 with WSLg (Windows 11) | ⚠️ May work - see WSL section below |
| WSL 1 or WSL without WSLg | ❌ Will not work - no display support |
| macOS | ❌ Not supported - eSim 2.5 is Linux only |

> **⚠️ WSL Warning:** This plugin requires KiCad GUI, eSim GUI, and ngspice - all graphical applications. WSL without WSLg display support will not work. VirtualBox Ubuntu is the fully tested and recommended environment.

---

## Installation

### Option A - VirtualBox Ubuntu (Recommended)

#### Step 1 - Set up VirtualBox

- Download VirtualBox from https://virtualbox.org
- Download Ubuntu 24.04 LTS ISO from https://ubuntu.com/download/desktop
- Create a VM with these settings:

| Setting | Value |
|---|---|
| RAM | 4096 MB minimum (8192 recommended) |
| Storage | 40 GB VDI |
| Graphics Controller | **VMSVGA** ← critical, not VBoxVGA |
| Video Memory | 256 MB |
| 3D Acceleration | Enabled |

#### Step 2 - Install KiCad 8.0

```bash
sudo apt update
sudo apt install -y kicad
kicad-cli --version   # Should show: Application: kicad-cli 8.0.x
```

#### Step 3 - Install eSim 2.5

```bash
cd ~/Downloads
wget https://static.fossee.in/esim/installation-files/eSim-2.5.zip
unzip eSim-2.5.zip
cd eSim-2.5
chmod +x install-eSim.sh
./install-eSim.sh --install
# Wait 5-10 minutes

# Verify installation
ls ~/Downloads/eSim-2.5/src/frontEnd/Application.py
ls ~/.esim/env/bin/python3
```

#### Step 4 - Install the plugin

```bash
cd ~
git clone https://github.com/ImranFarhat01/esim-bridge-plugin.git
cp -r ~/esim-bridge-plugin/esim_bridge ~/.local/share/kicad/8.0/scripting/plugins/

# Verify files are present (~50KB for esim_bridge.py)
ls -la ~/.local/share/kicad/8.0/scripting/plugins/esim_bridge/
```

#### Step 5 - Fix your username ⚠️ MANDATORY

The plugin has hardcoded paths with the developer's username `imran-farhat`. Replace with yours:

```bash
sed -i "s/imran-farhat/$(whoami)/g" ~/.local/share/kicad/8.0/scripting/plugins/esim_bridge/esim_bridge.py

# Verify - must return NO output
grep "imran-farhat" ~/.local/share/kicad/8.0/scripting/plugins/esim_bridge/esim_bridge.py
```

#### Step 6 - Fix `__init__.py` and create workspace

```bash
# Fix __init__.py
echo "from .esim_bridge import ESimBridgePlugin" > ~/.local/share/kicad/8.0/scripting/plugins/esim_bridge/__init__.py

# Create eSim workspace
mkdir -p ~/eSim-Workspace
echo '{"/home/'$(whoami)'/eSim-Workspace/esim_bridge_project": []}' > ~/eSim-Workspace/.projectExplorer.txt
```

#### Step 7 - Restart KiCad and verify

Open KiCad → PCB Editor → look for the eSim Bridge icon in the toolbar.  
If not visible: **Tools → External Plugins → Refresh Plugins**

---

### Option B - WSL Ubuntu (Windows Subsystem for Linux)

KiCad and system ngspice conflict on Ubuntu 24.04 in WSL. Follow these steps in exact order:

```bash
sudo apt update
sudo apt install kicad -y

# If libngspice-kicad conflict error appears:
sudo dpkg --remove --force-depends ngspice
sudo dpkg -i --force-overwrite /var/cache/apt/archives/libngspice-kicad_*.deb
sudo apt-get install -f -y

# Reinstall ngspice
sudo apt install ngspice -y
sudo dpkg -i --force-overwrite /var/cache/apt/archives/ngspice_*.deb
sudo apt-get install -f -y

# Verify both work
kicad-cli --version
ngspice --version
```

Then verify KiCad GUI actually opens:

```bash
kicad
# A KiCad window must appear - if you see display errors, use VirtualBox instead
```

Then follow Steps 3–7 from the VirtualBox section above (identical steps).

---

### One-Shot Install Script (clean Ubuntu system)

```bash
# Install KiCad
sudo apt update && sudo apt install -y kicad git

# Install eSim 2.5
cd ~/Downloads
wget https://static.fossee.in/esim/installation-files/eSim-2.5.zip
unzip eSim-2.5.zip && cd eSim-2.5
chmod +x install-eSim.sh && ./install-eSim.sh --install

# Install plugin
cd ~ && git clone https://github.com/ImranFarhat01/esim-bridge-plugin.git
cp -r ~/esim-bridge-plugin/esim_bridge ~/.local/share/kicad/8.0/scripting/plugins/

# Fix username
sed -i "s/imran-farhat/$(whoami)/g" ~/.local/share/kicad/8.0/scripting/plugins/esim_bridge/esim_bridge.py

# Fix __init__.py
echo "from .esim_bridge import ESimBridgePlugin" > ~/.local/share/kicad/8.0/scripting/plugins/esim_bridge/__init__.py

# Create workspace
mkdir -p ~/eSim-Workspace
echo '{"/home/'$(whoami)'/eSim-Workspace/esim_bridge_project": []}' > ~/eSim-Workspace/.projectExplorer.txt

echo "Done! Launch KiCad with: kicad"
```

---

## How to Use

### 4-Step Simulation Workflow

1. **Open KiCad** → draw schematic → save (`Ctrl+S`)
2. **Switch to PCB Editor** → click the **eSim Bridge icon** in the toolbar
3. **Select analysis type** and parameters → click **"Simulate in eSim →"**
4. **In eSim**: double-click `esim_bridge_project` in the left panel → **Simulate** → **Plot**

> **Note:** The plugin button appears in the **PCB Editor** toolbar, not the Schematic Editor.

### Analysis Types

| Analysis | Parameters | SPICE Command |
|---|---|---|
| Transient | Start Time, Step Time, Stop Time | `.tran 1us 10ms 0` |
| AC | Scale (dec/lin/oct), Start Freq, Stop Freq, Points | `.ac dec 100 1Hz 1MEGHz` |
| DC Sweep | Source Name, Start, Stop, Step | `.dc V1 0 5 0.1` |
| Operating Point | None needed | `.op` (results shown in popup) |

### Configuring a Voltage Source (VSIN)

Double-click the voltage source V1 in the schematic editor and set:

```
Sim.Type:   SIN
Sim.Params: dc=0 ampl=1 f=1k ac=1
```

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
| D | Diode / LED | `D1 anode cathode dled` (generic model auto-injected) |
| Q | BJT Transistor | `Q1 c b e model` |
| M | MOSFET | `M1 d g s b model` |
| U/X | Digital IC | Commented out - needs external `.subckt` model |

---

## File Structure

```
esim_bridge/
├── esim_bridge.py      # Main plugin code (~49 KB)
├── icon.png            # Plugin toolbar icon (4 KB)
└── __init__.py         # Package entry point
```

**Generated project files** (in `~/eSim-Workspace/esim_bridge_project/`):

```
esim_bridge_project/
├── esim_bridge_project.cir       # Pure SPICE netlist
├── esim_bridge_project.cir.out   # SPICE with .control block (used by ngspice)
├── esim_bridge_project.proj      # eSim project marker (empty)
├── analysis                      # Analysis command for eSim plotter
├── plot_data_v.txt               # Voltage simulation results
├── plot_data_i.txt               # Current simulation results
└── images/                       # Required by eSim data row display
```

---

## Useful Terminal Commands

```bash
# View generated SPICE file
cat ~/eSim-Workspace/esim_bridge_project/esim_bridge_project.cir.out

# Verify analysis file
cat ~/eSim-Workspace/esim_bridge_project/analysis

# Check simulation output data
head -10 ~/eSim-Workspace/esim_bridge_project/plot_data_v.txt

# Count data points
wc -l ~/eSim-Workspace/esim_bridge_project/plot_data_v.txt

# Run simulation manually in ngspice
ngspice -b ~/eSim-Workspace/esim_bridge_project/esim_bridge_project.cir.out

# View plugin log
cat ~/.local/share/kicad/esim_bridge.log

# Follow log in real time
tail -f ~/.local/share/kicad/esim_bridge.log

# Delete stale .raw file manually
rm -f ~/eSim-Workspace/esim_bridge_project/esim_bridge_project.raw

# Launch eSim manually
cd ~/Downloads/eSim-2.5/src/frontEnd
PYTHONPATH=/home/$(whoami)/Downloads/eSim-2.5/src ~/.esim/env/bin/python3 Application.py
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Plugin not in toolbar | KiCad not restarted | Restart KiCad → Tools → External Plugins → Refresh Plugins |
| `esim_bridge.py` is 0 bytes | Git clone got empty file | `rm -rf ~/esim-bridge-plugin && git clone https://github.com/ImranFarhat01/esim-bridge-plugin.git` |
| `__init__.py` is empty | File got corrupted | `echo "from .esim_bridge import ESimBridgePlugin" > ~/.local/share/kicad/8.0/scripting/plugins/esim_bridge/__init__.py` |
| eSim not found warning | eSim not at expected path | `ls ~/Downloads/eSim-2.5/src/frontEnd/Application.py` |
| `kicad-cli` not found | KiCad not installed | `sudo apt install kicad -y` |
| `ngspice` not found | Removed during KiCad fix | `sudo dpkg -i --force-overwrite /var/cache/apt/archives/ngspice_*.deb && sudo apt-get install -f -y` |
| `libngspice-kicad` conflict | Both packages own same file | `sudo dpkg --remove --force-depends ngspice && sudo dpkg -i --force-overwrite /var/cache/apt/archives/libngspice-kicad_*.deb` |
| Paths still say `imran-farhat` | `sed` command not run | `sed -i "s/imran-farhat/$(whoami)/g" ~/.local/share/kicad/8.0/scripting/plugins/esim_bridge/esim_bridge.py` |
| No schematic found | No project open in KiCad | Open a KiCad project before clicking the plugin |
| eSim opens with blank icons | Wrong VirtualBox display | Set VM display to VMSVGA + 256 MB video memory |
| Please select project first | No project selected in eSim | Double-click `esim_bridge_project` in eSim left panel |
| UTF-8 popup after simulate | Stale `.raw` binary file | Dismiss popup and click Simulate again - benign cosmetic issue |
| Flat graph at 0V | No voltage source in circuit | Add VSIN source with `Sim.Type=SIN` and `Sim.Params` set |
| KiCad display error in WSL | WSLg not supported | Use VirtualBox instead |

---

## Known Limitations

1. **OP analysis - no graph:** eSim 2.5 cannot plot `.op` results graphically. Node voltages are shown in a message box instead.

2. **UTF-8 popup (cosmetic):** A known cosmetic issue in eSim 2.5 causes a UTF-8 error popup when the plotter encounters a binary `.raw` file. This is an eSim-internal behavior, not a plugin defect. The simulation completes successfully. Dismiss the popup and proceed to plot.

3. **Manual project selection:** eSim 2.5 requires manually double-clicking the project in the project tree after opening.

4. **Linux only:** Plugin uses Linux paths. Not compatible with Windows or macOS.

5. **Single project folder:** All schematics share one eSim project folder (`esim_bridge_project`). Simulating a different schematic overwrites previous results.

6. **Basic components only:** Digital ICs (7400, 7402, etc.) and components requiring external `.subckt` model files are not supported and are commented out in the generated SPICE file.

7. **Username hardcoded:** Developer username (`imran-farhat`) must be replaced using the `sed` command in Step 5 of installation.

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
    "email": "imranfarhat.official@gmail.com",
    "fossee_contact": "contact-esim@fossee.in"
}
```

---

## License

GPL-3.0 - Free to use, modify, and distribute with attribution.
