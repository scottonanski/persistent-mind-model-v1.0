# 🚀 Getting Started with PMM (Persistent Mind Model)

Welcome to PMM! This guide will help you set up and run the Persistent Mind Model on your computer. Don't worry if you're not a tech expert - we'll take it step by step with simple instructions for Windows, Mac, and Linux.

## 📋 What You Need First

Before we start, make sure you have:
- 📶 An internet connection
- 💻 A computer (Windows, Mac, or Linux)
- ⏰ About 10-15 minutes

## 🪜 Step-by-Step Setup

### Step 1: Get the PMM Code 📥

First, we need to download PMM to your computer.

**For all systems:**
1. Open your computer's command line app:
   - **Windows:** Search for "Command Prompt" or "PowerShell"
   - **Mac:** Search for "Terminal"
   - **Linux:** Search for "Terminal"

2. Copy and paste this command (it's the same for all systems):
   ```
   git clone https://github.com/scottonanski/persistent-mind-model.git
   ```

3. Press Enter and wait for it to download.

4. Move into the PMM folder:
   ```
   cd persistent-mind-model
   ```

### Step 2: Set Up Your Python Environment 🐍

PMM needs Python to run. Let's create a special workspace for it.

**Windows:**
```
python -m venv .venv
.\.venv\Scripts\activate
```

**Mac/Linux:**
```
python -m venv .venv
source .venv/bin/activate
```

This creates a clean space where PMM can work without messing up your computer.

### Step 3: Install PMM's Tools 🔧

Now let's install the libraries PMM needs:

```
pip install -U pip
pip install -r requirements.txt
```

This installs PMM along with FastAPI, Rich, and the runtime dependencies.

### Step 4: Configure Model Access ⚙️

PMM needs a language model. Choose whichever option fits you best:

```
# Option A – OpenAI (fastest path if you have a key)
export OPENAI_API_KEY=your_key_here

# Option B – Local Ollama model (make sure `ollama serve` is running)
export PMM_PROVIDER=ollama
export PMM_MODEL=llama3
```

If you prefer storing settings in a file, copy `.env` to `.env.local`, add the variables there, and PMM will load them automatically.

### Step 5: Start PMM! 🎉

You're ready to go! Run this command:

```
python -m pmm.cli.chat
```

PMM will ask you to pick an AI model. You can choose:
- **OpenAI models** (like GPT-4) - needs an API key
- **Local models** (like Llama) - runs on your computer

## 🎮 Using PMM

Once PMM starts, you can:
- 💬 Chat with the AI
- 📊 See metrics with: `--@metrics on`
- 🔄 Switch models anytime with: `--@models`

## 🔧 Troubleshooting

**"I get an error!"**
- Make sure you're in the `persistent-mind-model` folder
- Check that you activated the virtual environment
- Try restarting your command line app

**"PMM won't start!"**
- Make sure you have Python installed (version 3.10 or higher)
- Try: `pip install -e .` again

**Need help?** Look at the full guide in the main README.md file!

## 🏆 You're Done!

Congratulations! 🎉 PMM is now running on your computer. It will remember everything and keep improving over time. Have fun exploring!
