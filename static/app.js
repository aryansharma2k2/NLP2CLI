const state = {
    outputModal: null,
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
    bindElements();
    state.outputModal = new bootstrap.Modal(elements.outputModal);

    elements.commandForm.addEventListener("submit", handleGenerate);
    elements.executeCommand.addEventListener("click", handleExecute);
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
            command: elements.editableCommand.value,
            directory: elements.directory.value,
            confirmed_high_risk: elements.confirmHighRisk.checked,
        });

        elements.outputText.textContent = response.output;
        renderAnalysis(response.analysis);
        prependHistory(elements.editableCommand.value, response.output, response.analysis);
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

function prependHistory(command, output, analysis) {
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

    const outputLabel = strongText("Output");
    const outputBlock = document.createElement("pre");
    outputBlock.textContent = output;

    item.append(heading, codeText(command), outputLabel, outputBlock);
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
