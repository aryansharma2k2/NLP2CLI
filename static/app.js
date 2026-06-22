const state = {
    outputModal: null,
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
    bindElements();
    state.outputModal = new bootstrap.Modal(elements.outputModal);

    elements.commandForm.addEventListener("submit", handleGenerate);
    elements.executeCommand.addEventListener("click", handleExecute);
    elements.refreshPreview.addEventListener("click", fetchPreview);

    Object.assign(elements, {
        exportBtn: document.getElementById("exportBtn"),
        historyEmpty: document.getElementById("historyEmpty"),
    });
});

function bindElements() {
    Object.assign(elements, {
        analysisFindings: document.getElementById("analysisFindings"),
        analysisSummary: document.getElementById("analysisSummary"),
        commandForm: document.getElementById("commandForm"),
        confirmHighRisk: document.getElementById("confirmHighRisk"),
        directory: document.getElementById("directory"),
        editableCommand: document.getElementById("editableCommand"),
        executeCommand: document.getElementById("executeCommand"),
        highRiskConfirmation: document.getElementById("highRiskConfirmation"),
        historyList: document.getElementById("historyList"),
        instruction: document.getElementById("instruction"),
        loadingSpinner: document.getElementById("loadingSpinner"),
        modelStatus: document.getElementById("modelStatus"),
        outputModal: document.getElementById("outputModal"),
        outputText: document.getElementById("outputText"),
        previewLabel: document.getElementById("previewLabel"),
        previewOutput: document.getElementById("previewOutput"),
        previewSection: document.getElementById("previewSection"),
        refreshPreview: document.getElementById("refreshPreview"),
        resultContainer: document.getElementById("resultContainer"),
        riskBadge: document.getElementById("riskBadge"),
        saferAlternative: document.getElementById("saferAlternative"),
    });
}

async function handleGenerate(event) {
    event.preventDefault();

    setLoading(true);
    elements.resultContainer.hidden = true;

    try {
        const response = await postJson("/generate", {
            instruction: elements.instruction.value,
            directory: elements.directory.value,
        });

        elements.editableCommand.value = response.generated_command;
        renderAnalysis(response.analysis);
        renderModelStatus(response.model_status);
        elements.resultContainer.hidden = false;
        elements.resultContainer.scrollIntoView({ behavior: "smooth", block: "start" });
        await fetchPreview();
    } catch (error) {
        showError(error);
    } finally {
        setLoading(false);
    }
}

async function handleExecute() {
    setLoading(true);

    try {
        const response = await postJson("/execute", {
            instruction: elements.instruction.value,
            command: elements.editableCommand.value,
            directory: elements.directory.value,
            confirmed_high_risk: elements.confirmHighRisk.checked,
        });

        elements.outputText.textContent = response.output;
        renderAnalysis(response.analysis);
        prependHistory(elements.instruction.value, elements.editableCommand.value, response.output, response.analysis);
        state.outputModal.show();
    } catch (error) {
        if (error.payload?.analysis) {
            renderAnalysis(error.payload.analysis);
        }
        showError(error);
    } finally {
        setLoading(false);
    }
}

async function postJson(url, payload) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
        const error = new Error(data.error || "Request failed. Please try again.");
        error.payload = data;
        throw error;
    }

    return data;
}

async function fetchPreview() {
    elements.previewSection.hidden = true;
    try {
        const result = await postJson("/preview", {
            command: elements.editableCommand.value,
            directory: elements.directory.value,
        });
        renderPreview(result);
    } catch (_) {
        // preview failure is non-fatal
    }
}

function renderPreview(result) {
    if (!result?.available) {
        elements.previewSection.hidden = true;
        return;
    }
    elements.previewSection.className = `preview-section preview-mode-${result.mode}`;
    elements.previewLabel.textContent = result.label;
    elements.previewOutput.textContent = result.output || "(no output)";
    elements.previewSection.hidden = false;
}

function renderAnalysis(analysis) {
    const risk = analysis?.risk || "unknown";
    elements.riskBadge.className = `risk-badge risk-${risk}`;
    elements.riskBadge.textContent = `${capitalize(risk)} risk`;

    elements.analysisSummary.textContent = analysis?.summary || "No analysis available.";
    elements.analysisFindings.replaceChildren(
        ...(analysis?.findings || []).map((finding) => {
            const item = document.createElement("li");
            item.textContent = finding;
            return item;
        })
    );

    if (analysis?.safer_alternative) {
        elements.saferAlternative.hidden = false;
        elements.saferAlternative.replaceChildren(
            strongText("Safer alternative: "),
            codeText(analysis.safer_alternative)
        );
    } else {
        elements.saferAlternative.hidden = true;
        elements.saferAlternative.replaceChildren();
    }

    elements.confirmHighRisk.checked = false;
    elements.highRiskConfirmation.hidden = !analysis?.requires_confirmation;
}

function renderModelStatus(status) {
    if (!status) {
        elements.modelStatus.hidden = true;
        elements.modelStatus.textContent = "";
        return;
    }

    elements.modelStatus.hidden = false;
    if (status.provider === "fallback") {
        elements.modelStatus.textContent = "Using local fallback rules because the model is unavailable.";
        return;
    }

    elements.modelStatus.textContent = `Generated with ${status.model_id}.`;
}

function prependHistory(instruction, command, output, analysis) {
    if (elements.historyEmpty) {
        elements.historyEmpty.hidden = true;
    }
    if (elements.exportBtn) {
        elements.exportBtn.hidden = false;
    }

    const item = document.createElement("li");
    item.className = "history-item";

    const heading = document.createElement("div");
    heading.className = "history-heading";
    heading.append(strongText("Command"));

    if (analysis?.risk) {
        const badge = document.createElement("span");
        badge.className = `risk-badge risk-${analysis.risk}`;
        badge.textContent = `${analysis.risk} risk`;
        heading.append(badge);
    }

    const children = [heading];

    if (instruction) {
        const intentEl = document.createElement("p");
        intentEl.className = "history-instruction";
        intentEl.textContent = instruction;
        children.push(intentEl);
    }

    const outputLabel = strongText("Output");
    const outputBlock = document.createElement("pre");
    outputBlock.textContent = output;

    children.push(codeText(command), outputLabel, outputBlock);
    item.append(...children);
    elements.historyList.prepend(item);
}

function setLoading(isLoading) {
    elements.loadingSpinner.hidden = !isLoading;
}

function showError(error) {
    alert(error.message || "Something went wrong. Please try again.");
}

function capitalize(value) {
    return value.charAt(0).toUpperCase() + value.slice(1);
}

function strongText(value) {
    const element = document.createElement("strong");
    element.textContent = value;
    return element;
}

function codeText(value) {
    const element = document.createElement("code");
    element.textContent = value;
    return element;
}
