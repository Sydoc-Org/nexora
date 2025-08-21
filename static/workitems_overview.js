function logAction(actionType, resourceId = null, details = null) {
  fetch("/log_action", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      action_type: actionType,
      resource_id: resourceId,
      details: details,
    }),
  }).catch((err) => console.error("Logging failed:", err));
}

// Search functionality
document.getElementById("searchInput").addEventListener("keyup", function () {
  closeAllDetails();
  const searchTerm = this.value.toLowerCase();
  const rows = document.querySelectorAll(".workitem-row");
  let visibleCount = 0;

  rows.forEach((row) => {
    const text = row.textContent.toLowerCase();
    if (text.includes(searchTerm)) {
      row.style.display = "";
      visibleCount++;
    } else {
      row.style.display = "none";
    }
  });

  document.getElementById("showingCount").textContent = visibleCount;
});

// Status filter functionality
document.getElementById("statusFilter").addEventListener("change", function () {
  closeAllDetails();
  const selectedStatus = this.value;
  const rows = document.querySelectorAll(".workitem-row");
  let visibleCount = 0;

  rows.forEach((row) => {
    const status = row.getAttribute("data-status");
    const workitemId = row.getAttribute("data-id");
    const detailsRow = document.getElementById(`details-${workitemId}`);
    const chevron = document.getElementById(`chevron-${workitemId}`);

    if (selectedStatus === "" || status === selectedStatus) {
      row.style.display = "";
      visibleCount++;
    } else {
      row.style.display = "none";

      // Hide details if open
      if (detailsRow) detailsRow.style.display = "none";
      if (chevron) {
        chevron.classList.remove("glyphicon-chevron-down-custom");
        chevron.classList.add("glyphicon-chevron-up-custom");
      }
    }
  });

  document.getElementById("showingCount").textContent = visibleCount;
});

function closeAllDetails() {
  document.querySelectorAll("[id^='details-']").forEach((detailsRow) => {
    detailsRow.style.display = "none";
  });
  document.querySelectorAll("[id^='chevron-']").forEach((chevron) => {
    chevron.classList.remove("glyphicon-chevron-down-custom");
    chevron.classList.add("glyphicon-chevron-up-custom");
  });
}

// Table sorting functionality
function sortTable(columnIndex) {
  const table = document.getElementById("workitemsTable");
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);

  // Only select workitem rows for sorting
  const workitemRows = Array.from(tbody.querySelectorAll(".workitem-row"));

  workitemRows.sort((a, b) => {
    const aValue = a.cells[columnIndex].textContent.trim();
    const bValue = b.cells[columnIndex].textContent.trim();

    // Handle numeric values (like ID)
    if (columnIndex === 0) {
      return (
        parseInt(aValue.replace("#", "")) - parseInt(bValue.replace("#", ""))
      );
    }

    // Handle dates
    if (columnIndex === 2) {
      return new Date(aValue) - new Date(bValue);
    }

    // Handle text
    return aValue.localeCompare(bValue);
  });

  rows.forEach((row) => tbody.appendChild(row));
}

// View details functionality
async function toggleDetails(workitemId) {
  const detailsRow = document.getElementById(`details-${workitemId}`);
  const chevron = document.getElementById(`chevron-${workitemId}`);
  const isOpen = detailsRow.style.display === "table-row";

  if (!isOpen) {
    logAction("views_workitem_details", workitemId);
    detailsRow.style.display = "table-row";
    chevron.classList.remove("glyphicon-chevron-up-custom");
    chevron.classList.add("glyphicon-chevron-down-custom");

    // fetch API
    try {
      const res = await fetch(`/allstatesfromoneworkitem/${workitemId}`);
      const data = await res.json();
      if (res.ok) {
        renderTimeline(workitemId, data);
      } else {
        document.getElementById(
          `timeline-wrapper-${workitemId}`
        ).innerHTML = `<p class="text-red-500">Fehler: ${data.error}</p>`;
      }
    } catch (err) {
      document.getElementById(
        `timeline-wrapper-${workitemId}`
      ).innerHTML = `<p class="text-red-500">API Fehler</p>`;
      console.error(err);
    }
  } else {
    detailsRow.style.display = "none";
    chevron.classList.remove("glyphicon-chevron-down-custom");
    chevron.classList.add("glyphicon-chevron-up-custom");
  }
}

function renderTimeline(workitemId, states) {
  const baseStates = ["Ready", "In Progress", "Done", "Collected"];
  const allStates = states.map((s) => s.state);

  // Map für schnellen Zugriff auf State-Objekte
  const stateMap = {};
  states.forEach((s) => {
    stateMap[s.state] = s;
  });

  // Letzten State bestimmen
  const currentState = states.length
    ? states[states.length - 1].state
    : "Ready";
  const readyStateObj = stateMap["Ready"] || null;

  // Logik für "Demanded" einfügen oder nicht
  let showDemanded = false;
  let infoText = "";

  if (readyStateObj && readyStateObj.DemandedBy) {
    // Bereits demanded
    showDemanded = true;
  } else {
    if (currentState === "Ready") {
      infoText = "Ready to Demand";
    } else if (["In Progress", "Done", "Collected"].includes(currentState)) {
      infoText = "Demand not possible";
    }
  }

  // Falls erlaubt, "Demanded" einfügen
  if (showDemanded) {
    const readyIndex = allStates.indexOf("Ready");
    if (readyIndex !== -1) {
      allStates.splice(readyIndex + 1, 0, "Demanded");
    } else {
      allStates.unshift("Demanded");
    }
  }

  // Fehlende Basisstates ergänzen
  baseStates.forEach((s) => {
    if (!allStates.includes(s)) allStates.push(s);
  });

  // Duplikate entfernen und Reihenfolge nach baseStates (plus Demanded) festlegen
  const orderedStates = [];
  baseStates.forEach((state) => {
    if (allStates.includes(state)) {
      orderedStates.push(state);
    }
  });
  if (allStates.includes("Demanded")) {
    const readyIndex = orderedStates.indexOf("Ready");
    if (readyIndex !== -1) {
      orderedStates.splice(readyIndex + 1, 0, "Demanded");
    } else {
      orderedStates.unshift("Demanded");
    }
  }

  // Aktiven Index berechnen
  let activeIndex = orderedStates.indexOf(currentState);

  if (currentState === "Collected") {
    // Bei "Collected" alle Punkte aktivieren
    activeIndex = orderedStates.length - 1;
  } else if (
    showDemanded &&
    orderedStates.includes("Demanded") &&
    readyStateObj &&
    readyStateObj.DemandedBy
  ) {
    // Wenn demanded, aktiver Punkt ist "Demanded"
    activeIndex = orderedStates.indexOf("Demanded");
  }

  // Container leeren
  const inputsContainer = document.getElementById(
    `timeline-inputs-${workitemId}`
  );
  const descContainer = document.getElementById(
    `timeline-descriptions-${workitemId}`
  );
  inputsContainer.innerHTML = "";
  descContainer.innerHTML = "";

  // Timeline Punkte rendern
  orderedStates.forEach((state, index) => {
    let found =
      state === "Demanded"
        ? readyStateObj || states[0] || null
        : stateMap[state] || null;

    const containerDiv = document.createElement("div");
    containerDiv.style.display = "flex";
    containerDiv.style.flexDirection = "column";
    containerDiv.style.alignItems = "center";
    containerDiv.style.margin = "0 6px";

    // Label erstellen
    const labelSpan = document.createElement("span");
    labelSpan.classList.add(
      "px-2",
      "py-1",
      "text-xs",
      "font-semibold",
      "rounded-full"
    );
    labelSpan.style.marginBottom = "15px";
    labelSpan.style.fontSize = "14px";
    labelSpan.style.padding = "8px 12px";

    switch (state) {
      case "Collected":
        labelSpan.classList.add("bg-purple-100", "text-purple-800");
        labelSpan.textContent = "Collected";
        break;
      case "Done":
        labelSpan.classList.add("bg-green-100", "text-green-800");
        labelSpan.textContent = "Done";
        break;
      case "In Progress":
        labelSpan.classList.add("bg-yellow-100", "text-yellow-800");
        labelSpan.textContent = "In Progress";
        break;
      case "Ready":
        labelSpan.classList.add("bg-blue-100", "text-blue-800");
        labelSpan.textContent = "Ready";
        break;
      case "Demanded":
        labelSpan.classList.add("bg-red-100", "text-red-800");
        labelSpan.textContent = "Demanded";
        break;
      default:
        labelSpan.textContent = state;
    }

    containerDiv.appendChild(labelSpan);

    // Punkt
    const inputDiv = document.createElement("div");
    inputDiv.classList.add("input");

    if (index <= activeIndex) {
      if (state === "Demanded") {
        if (readyStateObj && readyStateObj.DemandedBy) {
          inputDiv.classList.add("active");
        }
      } else {
        inputDiv.classList.add("active");
      }
    }

    if (index < orderedStates.length - 1) {
      const lineDiv = document.createElement("div");
      lineDiv.classList.add("timeline-line");
      containerDiv.appendChild(lineDiv);
    }

    // Datum/Zeit
    const span = document.createElement("span");
    span.setAttribute("data-info", state);
    if (found && found.datetime) {
      const d = new Date(found.datetime);
      const dateStr = d.toLocaleDateString("de-DE", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      });
      const timeStr = d.toLocaleTimeString("de-DE", {
        hour: "2-digit",
        minute: "2-digit",
      });
      span.innerHTML = `<div class="date">${dateStr}</div><div class="time">${timeStr}</div>`;
    } else {
      span.innerHTML = `<div class="date"></div><div class="time"></div>`;
    }

    inputDiv.appendChild(span);
    containerDiv.appendChild(inputDiv);

    inputsContainer.appendChild(containerDiv);

    // Beschreibungsplatzhalter
    const p = document.createElement("p");
    if (index === activeIndex) p.classList.add("active");
    descContainer.appendChild(p);
  });

  // Info-Text einfügen falls nötig
  if (infoText) {
    const infoP = document.createElement("p");
    infoP.classList.add("text-sm", "text-gray-500", "mt-2");
    infoP.style.marginTop = "-20px";
    infoP.style.marginBottom = "40px";
    infoP.textContent = infoText;
    infoP.classList.remove("text-gray-500");
    infoP.classList.add("text-red-500");
    descContainer.appendChild(infoP);
  }

  animateColoredLine(
    workitemId,
    currentState,
    readyStateObj ? readyStateObj.DemandedBy : null
  );
}

function animateColoredLine(workitemId, currentStatus, demandedBy) {
  const inputsContainer = document.getElementById(
    `timeline-inputs-${workitemId}`
  );

  // Erst auf 0 setzen (unsichtbar)
  inputsContainer.style.setProperty("--active-line-width", "0px");

  // Kurz warten, dann auf Zielwert setzen
  setTimeout(() => {
    updateColoredLine(workitemId, currentStatus, demandedBy);
  }, 50);
}

function updateColoredLine(workitemId, currentStatus, demandedBy) {
  const inputsContainer = document.getElementById(
    `timeline-inputs-${workitemId}`
  );
  const inputs = inputsContainer.querySelectorAll(".input");

  const statusColors = {
    Collected: "#D8B4FE",
    Done: "#86EFAC",
    "In Progress": "#FDE68A",
    "Ready not demanded": "#93C5FD",
    "Ready and Demanded": "#FCA5A5",
  };

  const inactiveColor = "#ccc";

  let lastActiveIndex = -1;
  inputs.forEach((el, i) => {
    if (el.classList.contains("active")) lastActiveIndex = i;
  });

  if (lastActiveIndex < 0) {
    inputsContainer.style.setProperty("--active-line-width", "0px");
    inputsContainer.style.setProperty("--active-line-color", inactiveColor);
    return;
  }

  let activeColor;
  if (currentStatus === "Ready") {
    if (demandedBy) {
      activeColor = statusColors["Ready and Demanded"];
    } else {
      activeColor = statusColors["Ready not demanded"];
    }
  } else {
    activeColor = statusColors[currentStatus] || "#999";
  }

  const containerWidth = inputsContainer.offsetWidth;
  const padding = 12.5; // wie im CSS-Padding
  const numberOfPoints = inputs.length;
  const innerWidth = containerWidth - 2 * padding;
  const step = innerWidth / (numberOfPoints - 1);

  let finalWidth;

  if (currentStatus === "Collected") {
    finalWidth = containerWidth - padding;
  } else if (lastActiveIndex < numberOfPoints - 1) {
    finalWidth = padding + step * lastActiveIndex + step / 2;
  } else {
    finalWidth = padding + step * lastActiveIndex;
  }

  inputsContainer.style.setProperty("--active-line-width", `${finalWidth}px`);
  inputsContainer.style.setProperty("--active-line-color", activeColor);
}

// Export to CSV functionality
function exportToCSV() {
  logAction("CSVexport_workitems", null, { export_type: "workitems" });
  let csv = [];
  const table = document.getElementById("workitemsTable");
  const rows = table.querySelectorAll(
    'tr:not([style*="display: none"]):not(.details-row)'
  );

  // Add headers
  const headers = Array.from(rows[0].cells)
    .slice(0, -1)
    .map((cell) => cell.textContent.trim());
  csv.push(headers.join(";"));

  // Add rows
  for (let i = 1; i < rows.length; i++) {
    const row = Array.from(rows[i].cells)
      .slice(0, -1)
      .map((cell) => {
        let text = cell.textContent.trim();
        if (/[;\n"]/.test(text)) {
          text = `"${text.replace(/"/g, '""')}"`;
        }
        return text;
      });
    csv.push(row.join(";"));
  }

  // Download CSV
  const csvString = csv.join("\n");
  const blob = new Blob([csvString], { type: "text/csv" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `workitems_${new Date().toISOString().split("T")[0]}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

// Demand workitem functionality
function demandWorkitem(workitemId) {
  // Placeholder: Implement the demand workitem logic here
}
