// Search functionality
document.getElementById("searchInput").addEventListener("keyup", function () {
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
  const selectedStatus = this.value;
  const rows = document.querySelectorAll(".workitem-row");
  let visibleCount = 0;

  rows.forEach((row) => {
    const status = row.getAttribute("data-status");
    if (selectedStatus === "" || status === selectedStatus) {
      row.style.display = "";
      visibleCount++;
    } else {
      row.style.display = "none";
    }
  });

  document.getElementById("showingCount").textContent = visibleCount;
});

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
    detailsRow.style.display = "table-row";
    chevron.classList.remove("glyphicon-chevron-down-custom");
    chevron.classList.add("glyphicon-chevron-up-custom");

    // API abrufen
    try {
      const res = await fetch(`/allstatesfromoneworkitem/${workitemId}`);
      const data = await res.json();
      if (res.ok) {
        renderTimeline(workitemId, data);
      } else {
        document.getElementById(`timeline-wrapper-${workitemId}`).innerHTML =
          `<p class="text-red-500">Fehler: ${data.error}</p>`;
      }
    } catch (err) {
      document.getElementById(`timeline-wrapper-${workitemId}`).innerHTML =
        `<p class="text-red-500">API Fehler</p>`;
      console.error(err);
    }
  } else {
    detailsRow.style.display = "none";
    chevron.classList.remove("glyphicon-chevron-up-custom");
    chevron.classList.add("glyphicon-chevron-down-custom");
  }
}

function renderTimeline(workitemId, states) {
  const baseStates = ["Ready", "In Progress", "Done", "Collected"];
  const allStates = states.map(s => s.state);

  // "Demanded" immer nach "Ready" einfügen (oder am Anfang, falls Ready nicht vorhanden)
  if (!allStates.includes("Demanded")) {
    const readyIndex = allStates.indexOf("Ready");
    if (readyIndex !== -1) {
      allStates.splice(readyIndex + 1, 0, "Demanded");
    } else {
      allStates.unshift("Demanded");
    }
  }

  // Fehlende Basistates ergänzen
  baseStates.forEach(s => {
    if (!allStates.includes(s)) allStates.push(s);
  });

  // Duplikate entfernen
  const uniqueStates = [...new Set(allStates)];

  // Map für schnellen Zugriff auf State-Objekte
  const stateMap = {};
  states.forEach(s => {
    stateMap[s.state] = s;
  });

  // Letzten State bestimmen
  const currentState = states.length ? states[states.length - 1].state : "Ready";

  // Referenz auf Ready State Objekt
  const readyStateObj = stateMap["Ready"] || null;
  const demandedIdx = uniqueStates.indexOf("Demanded");

  // Aktiven Index berechnen
  let activeIndex = uniqueStates.indexOf(currentState);

  if (readyStateObj) {
    if (readyStateObj.DemandedBy) {
      // Wenn Demand gesetzt ist, Demand als aktiv markieren
      if (demandedIdx !== -1) activeIndex = demandedIdx;
    } else {
      if (currentState === "Ready") {
        activeIndex = uniqueStates.indexOf("Ready");
      } else if (["In Progress", "Done", "Collected"].includes(currentState)) {
        // Auch wenn DemandedBy nicht gesetzt, aber State höher als Ready, Demand aktiv
        if (demandedIdx !== -1) activeIndex = demandedIdx;
      }
    }
  }

  // Für höhere States In Progress, Done, Collected aktive Punkte bis dahin farbig machen
  if (["In Progress", "Done", "Collected"].includes(currentState)) {
    activeIndex = uniqueStates.indexOf(currentState);
  }

  // Container leeren
  const inputsContainer = document.getElementById(`timeline-inputs-${workitemId}`);
  const descContainer = document.getElementById(`timeline-descriptions-${workitemId}`);
  inputsContainer.innerHTML = "";
  descContainer.innerHTML = "";

  uniqueStates.forEach((state, index) => {
  
  let found = state === "Demanded" ? (readyStateObj || states[0] || null) : stateMap[state] || null;
  // Container für Label + Punkt
  const containerDiv = document.createElement("div");
  containerDiv.style.display = "flex";
  containerDiv.style.flexDirection = "column";
  containerDiv.style.alignItems = "center";
  containerDiv.style.margin = "0 6px"; // optional: Abstand der Punkte

  // Label Span erzeugen
  const labelSpan = document.createElement("span");
  labelSpan.classList.add("px-2", "py-1", "text-xs", "font-semibold", "rounded-full");
  labelSpan.style.marginBottom = "15px";
  labelSpan.style.fontSize = "14px"; // größere Schrift
  labelSpan.style.padding = "8px 12px"; // mehr Innenabstand

  // Label Text und Farben (nur Label, NICHT Punktfarben!)
  switch(state) {
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
      if (readyStateObj && readyStateObj.DemandedBy) {
        labelSpan.classList.add("bg-red-100", "text-red-800");
        labelSpan.textContent = "Ready";
      } else {
        labelSpan.classList.add("bg-blue-100", "text-blue-800");
        labelSpan.textContent = "Ready";
      }
      break;
    case "Demanded":
      labelSpan.classList.add("bg-orange-100", "text-orange-800");
      labelSpan.textContent = "Demanded";
      break;
    default:
      labelSpan.textContent = state;
  }

  containerDiv.appendChild(labelSpan);

  // Punkt DIV wie vorher, mit den bisherigen Farben!
  const inputDiv = document.createElement("div");
  inputDiv.classList.add("input");

  // Punkt färben wie bisher (active, state-Klasse etc.)
  if (index <= activeIndex) {
    if (state === "Demanded") {
      if ((readyStateObj && readyStateObj.DemandedBy) || ["In Progress", "Done", "Collected"].includes(currentState)) {
        inputDiv.classList.add("active");
      }
    } else {
      inputDiv.classList.add("active");
    }
  }
  if (index < uniqueStates.length - 1) {
  const lineDiv = document.createElement("div");
  lineDiv.classList.add("timeline-line"); // Klasse für die Linie
  containerDiv.appendChild(lineDiv);      // Linie direkt nach Punkt einfügen
}

  // Rest wie gehabt: Datum & Uhrzeit im inneren span
  const span = document.createElement("span");
  span.setAttribute("data-info", state);

  if (found) {
    if (state === "Demanded") {
      if (readyStateObj && readyStateObj.DemandedBy === null && currentState === "Ready") {
        span.innerHTML = `<div class="date"></div><div class="time"></div>`;
        inputDiv.title = "Demanded (noch nicht gesetzt)";
      } else {
        const d = new Date(found.datetime);
        const dateStr = d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
        const timeStr = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
        span.innerHTML = `<div class="date">${dateStr}</div><div class="time">${timeStr}</div>`;
        inputDiv.title = readyStateObj && readyStateObj.DemandedBy ? `Demanded by: ${readyStateObj.DemandedBy}` : "Demanded (kein Info)";
      }
    } else {
      if (found.datetime) {
        const d = new Date(found.datetime);
        const dateStr = d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
        const timeStr = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
        span.innerHTML = `<div class="date">${dateStr}</div><div class="time">${timeStr}</div>`;
      } else {
        span.innerHTML = `<div class="date"></div><div class="time"></div>`;
      }
    }
  } else {
    span.innerHTML = `<div class="date"></div><div class="time"></div>`;
  }

  inputDiv.appendChild(span);
  containerDiv.appendChild(inputDiv);

  inputsContainer.appendChild(containerDiv);

  // Beschreibungspunkte bleiben unverändert
  const p = document.createElement("p");
  if (index === activeIndex) p.classList.add("active");
  descContainer.appendChild(p);
});
  animateColoredLine(workitemId, currentState);
}

function animateColoredLine(workitemId, currentStatus) {
  const inputsContainer = document.getElementById(`timeline-inputs-${workitemId}`);

  // Erst auf 0 setzen (unsichtbar)
  inputsContainer.style.setProperty("--active-line-width", "0px");

  // Kurz warten, dann auf Zielwert setzen
  setTimeout(() => {
    updateColoredLine(workitemId, currentStatus);
  }, 50);
}

// Funktion zum Anpassen der farbigen Linie
function updateColoredLine(workitemId, currentStatus) {
  const inputsContainer = document.getElementById(`timeline-inputs-${workitemId}`);
  const inputs = inputsContainer.querySelectorAll(".input");

  const statusColors = {
  "Collected": "#D8B4FE",       
  "Done": "#86EFAC",            
  "In Progress": "#FDE68A",     
  "Ready not demanded": "#93C5FD", 
  "Ready and Demanded": "#FCA5A5" 
};


  const activeColor = statusColors[currentStatus] || "#999";
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

  const containerWidth = inputsContainer.offsetWidth;
  const numberOfPoints = inputs.length;

  // Abstand zwischen Punkten (Punktanzahl - 1 Lücken)
  const step = containerWidth / (numberOfPoints - 1);

  // Breite bis zum linken Rand des aktiven Punktes
  const widthUntilPoint = step * lastActiveIndex;

  // Breite + halbe Punktbreite (angenommen Punkt 20px breit)
  const pointDiameter = 20; // Falls deine Punkte andere Größe haben, passe hier an

  const finalWidth = widthUntilPoint + pointDiameter / 2;

  inputsContainer.style.setProperty("--active-line-width", `${finalWidth}px`);
  inputsContainer.style.setProperty("--active-line-color", activeColor);
}


// Export to CSV functionality
function exportToCSV() {
  let csv = [];
  const table = document.getElementById("workitemsTable");
  const rows = table.querySelectorAll('tr:not([style*="display: none"]):not(.details-row)');

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
