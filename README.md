# Haste

### Installation

**1) Create virtual environment**

```bash
python3 -m venv ~/.cli-venv
source ~/.cli-venv/bin/activate
pip3 install pygithub requests
```

**2) Clone this repository**

```bash
cd ~/code
git clone https://github.com/mimukr/haste.git
```

**3) Add alias**

```bash
vim ~/.zshrc
alias haste="~/.cli-venv/bin/python3 ~/code/haste/haste.py"
```

### Usage

**Example**

```bash
haste "beep boop"
```
