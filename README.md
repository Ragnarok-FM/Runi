## Development Setup

Follow these steps to set up a local development environment.

### 1. Create a Virtual Environment

```bash
python -m venv .venv
```

---

### 2. Activate the Virtual Environment

**Windows (PowerShell)**

```powershell
.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt)**

```cmd
.venv\Scripts\activate.bat
```

**Linux / macOS**

```bash
source .venv/bin/activate
```

---

### 3. Install Dependencies

Install the project in editable mode:

```bash
pip install -e .
```

---

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_token_here
```

---

### 5. Run the Bot

```bash
runi
```

---
