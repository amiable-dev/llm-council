# How to Use LLM Council with Claude Desktop

This guide summarizes the exact steps to fire up your LLM Council and connect it to Claude Desktop for high-quality, multi-model deliberation.

## 1. Start the MCP Server
Because Claude Desktop needs a live connection to your project, you must ensure the project is ready to be called. Open a terminal and run the following command first to check for any errors:

```powershell
C:\Users\carte\.local\bin\uv.exe --directory "c:\git_projects\llm-council" run llm-council
```
*(If it starts without errors, you are good to go!)*

## 2. Connect Claude Desktop
Once Claude Desktop is running, you need to ensure it "sees" your local council.
1. Open a **fresh chat** in Claude Desktop.
2. Type exactly this command:
   > `/mcp`
3. Verify that **`llm-council`** appears in the list of active servers.
4. (Optional) Click the **🔌 plug icon** in the bottom-right of the chat box to confirm it is connected.

## 3. Ask the Council
Now you can simply talk to Claude and ask him to use the council.

### Example Queries:
* **Classic Query**: *"Ask the LLM Council about [Your Question]."*
* **Deep Details**: *"Consult the Council about [Your Question] and **show me the Stage 1 details and thinking**."*
* **Devil's Advocate**: *"Ask the Council to **audit** its consensus on [Problem] using the **Devil's Advocate**."* (This triggers `adversarial_mode`).
* **Statistical Dissent**: *"Ask the Council about [Hard Problem] and **include any dissenting opinions** from the peer review stage."* (This triggers `include_dissent`).

## 4. Key Configuration
* **Project Location**: `c:\git_projects\llm-council`
* **Models Used**: Open your `llm_council.yaml` to customize which models (GPT, Claude, Gemini, Meta) participate in each tier.
* **API Key**: Managed securely via the Windows Credential Manager.

---
*Note: If the Council doesn't appear after a code change, remember to **fully quit** Claude Desktop from the System Tray and relaunch it.*

---

## 5. Alternative: Run a Terminal Query
If you don't want to use Claude Desktop, you can get a synthesized answer directly from your PowerShell terminal:

```powershell
C:\Users\carte\.local\bin\uv.exe --directory "c:\git_projects\llm-council" run python query.py "What is the consensus on [Problem]?"
```

### Advanced Flags:
* **`--details`**: Displays the raw, unedited Stage 1 responses from every model in the council.
* **`--confidence [quick|balanced|high|reasoning]`**: Determines which tier of models are called.
* **`--no-cache`**: Bypasses the cache and forces a fresh deliberation.
* **`--adversary`**: Enables the **Forensic Auditor** (Devil's Advocate) who proactively finds flaws in the group's logic before the final synthesis.
* **`--dissent`**: Enables **Constructive Dissent** extraction, which mathematically identifies minority opinions from the voting phase.

---

## 6. Configuring Your Council (`llm_council.yaml`)
You have full control over which models participate in the deliberation by editing the `llm_council.yaml` file in the project root.

### How to use the YAML:
*   **Tiers**: The file is divided into `quick`, `balanced`, and `high` tiers. 
*   **Model Pools**: Add or remove model IDs (from [OpenRouter](https://openrouter.ai/models)) in the `models:` list for each tier.
*   **Timeouts**: You can adjust `timeout_seconds` if you find certain models are consistently timing out.
*   **Stick to Your List**: The `model_intelligence: enabled: false` setting ensures the council stays strictly within the models you've listed (to avoid getting charged for expensive "futuristic" models).

---

## 7. Transparency & Detail Levels
Depending on whether you use the Terminal or Claude Desktop, you have different options for seeing "under the hood" of the council:

| Feature | Terminal | Claude |
| :--- | :---: | :---: |
| **Raw Stage 1 Texts** | ✅ | ✅ |
| **Borda Ranking Scores** | ✅ | ✅ |
| **Statistical Dissent** | ✅ | ✅ |
| **Forensic Auditor (DA)** | ✅ | ✅ |
| **Model Latency/Status** | ❌ | ✅ |
| **Advanced Quality Metrics** | ❌ | ✅ |

---

## ✅ Final Verification Checklist
Before you close your own documentation mission:
1. [ ] **Launch Test**: Open Claude Desktop and confirm the "Council" tool is listed.
2. [ ] **Execution Test**: Ask the Council a simple question in the UI.
3. [ ] **Log Test**: Check the terminal to confirm the `run_mcp.bat` bridge is active.
