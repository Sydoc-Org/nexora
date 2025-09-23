const API_PREFIX = window.location.href.includes("sydocportal") ? "/sydocportal/" : "/";

function logAction(actionType, resourceId = null, details = null) {
  // fetch("/sydocportal/log_action", {
  fetch(`${API_PREFIX}log_action`, {
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

const supportLink = document.querySelector(".support-link");

supportLink.addEventListener("click", function () {
  logAction("click_support_link");
});

async function updateRecentActivity() {
  const list = document.getElementById("recent-activity-list");
  //list.innerHTML = '<li class="text-gray-500">Loading...</li>';

  fetch(`${API_PREFIX}api/recent_activity`)
    .then((response) => {
      if (!response.ok) {
        throw new Error("Error fetching recent activity");
      }
      return response.json();
    })
    .then((data) => {
      list.innerHTML = ""; // Liste leeren

      if (!Array.isArray(data) || data.length === 0) {
        list.innerHTML =
          '<li class="text-gray-500">No recent activity found.</li>';
        return;
      }

      data.forEach((activity) => {
        const li = document.createElement("li");
        li.className = "flex items-start space-x-3";

        let iconHTML = "";
        let textMessage = "";
        const status = activity.state;

        if (status === "Ready") {
          iconHTML = `
                        <div class="h-6 w-6 flex-shrink-0 bg-blue-100 text-blue-600 flex items-center justify-center rounded-full mr-3 mt-1">
                            <i class="fa-solid fa-hourglass-start text-xs"></i>
                        </div>
                    `;
          textMessage = `Barcode <span class="font-bold">${activity.Barcode}</span> is ready`;
        } else if (status === "In Progress") {
          iconHTML = `
                        <div class="h-6 w-6 flex-shrink-0 bg-yellow-100 text-yellow-600 flex items-center justify-center rounded-full mr-3 mt-1">
                            <i class="fa-solid fa-spinner text-xs"></i>
                        </div>
                    `;
          textMessage = `Processing for Barcode <span class="font-bold">${activity.Barcode}</span> has started.`;
        } else if (status === "Done") {
          iconHTML = `
                        <div class="h-6 w-6 flex-shrink-0 bg-indigo-100 text-indigo-600 flex items-center justify-center rounded-full mr-3 mt-1">
                            <i class="fas fa-file-upload text-xs"></i>
                        </div>
                    `;
          textMessage = `Barcode <span class="font-bold">${activity.Barcode}</span> has finished processing.`;
        } else if (status === "Collected") {
          iconHTML = `
                        <div class="h-6 w-6 flex-shrink-0 bg-green-100 text-green-600 flex items-center justify-center rounded-full mr-3 mt-1">
                            <i class="fas fa-check text-xs"></i>
                        </div>
                    `;
          textMessage = `Barcode <span class="font-bold">${activity.Barcode}</span> was just collected.`;
        } else {
          iconHTML = `
                        <div class="h-6 w-6 flex-shrink-0 bg-gray-300 text-gray-700 flex items-center justify-center rounded-full mr-3 mt-1">
                            <i class="fas fa-question text-xs"></i>
                        </div>
                    `;
          textMessage = `Unknown status for Barcode <span class="font-bold">${activity.Barcode}</span>.`;
        }

        li.innerHTML = `
                    ${iconHTML}
                    <div>
                        <p class="text-sm font-medium">${textMessage}</p>
                        <p class="text-xs text-gray-500">${activity.datetime}</p>
                    </div>
                `;

        list.appendChild(li);
      });
    })
    .catch((error) => {
      console.error("Error fetching recent activity:", error);
      list.innerHTML =
        '<li class="text-red-500">Error fetching recent activity.</li>';
    });
};

const activityDetails = {
  'InValidation': {
    icon: 'fa-solid fa-laptop-file',
    color: 'violet',
    text: 'In Validation'
  },
  'InExport': {
    icon: 'fa-solid fa-file-export',
    color: 'green',
    text: 'In Export'
  },
  'InImport': {
    icon: 'fa-solid fa-file-import',
    color: 'red',
    text: 'In Import'
  },
  'InExtraction': {
    icon: 'fa-solid fa-file-waveform',
    color: 'blue',
    text: 'In Extraction'
  },
  'InOCR': {
    icon: 'fa-solid fa-file-lines',
    color: 'sky',
    text: 'In OCR'
  },
  'InDBSaving': {
    icon: 'fa-solid fa-database',
    color: 'orange',
    text: 'In DB Saving'
  },
  'Processing': {
    icon: 'fa-solid fa-list-check',
    color: 'yellow',
    text: 'Processing'
  }
};

async function updateDocumentPreviewStats(caller) {
  let css_animation = (caller === undefined) ? "transition-all duration-500 ease-out" : "";

  const container = document.getElementById('document-preview-container');
  if (!container) {
    console.error('Error: The container with ID "document-preview-container" was not found.');
    return;
  }

  try {
    const response = await fetch(`${API_PREFIX}api/dashboard_stats_document_preview`);
    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`);
    }
    const rows = await response.json();
    container.innerHTML = '';

    if (rows.length === 0) {
      container.innerHTML = '<p class="text-gray-500">No active documents to display.</p>';
      return;
    }
    rows.forEach((row, index) => {
      const details = activityDetails[row.Activity] || activityDetails.default;
      const color = details.color;

      const cardElement = document.createElement('div');

      cardElement.className = `group bg-white p-4 rounded-xl shadow-lg flex items-center space-x-4 
                             ${css_animation} hover:shadow-2xl hover:-translate-y-1`;

      cardElement.innerHTML = `
        <div class="bg-${color}-100 text-${color}-600 h-16 w-16 flex-shrink-0 flex items-center justify-center
                     rounded-full text-2xl ${css_animation} group-hover:bg-${color}-500 group-hover:text-white">
            <i class="${details.icon}"></i>
        </div>
        <div>
            <h4 class="font-bold text-lg text-gray-800">Barcode ${row.Barcode}</h4>
            <p class="text-sm text-gray-500">Current Status:</p>
            <span class="bg-${color}-100 text-${color}-800 text-xs font-medium px-2.5 py-0.5 rounded-full">
                ${details.text}
            </span>
        </div>
    `;

      cardElement.classList.add('opacity-0', 'translate-y-4');

      container.appendChild(cardElement);

      const delay = index * 100;
      setTimeout(() => {
        cardElement.classList.remove('opacity-0', 'translate-y-4');
      }, delay);
    });

  } catch (error) {
    console.error("Failed to update document preview stats:", error);
    container.innerHTML = `<div class="text-center text-red-500 p-4">Error loading data.</div>`;
  }
};

function animateValue(element, start, end, duration) {
  let startTimestamp = null;
  const step = (timestamp) => {
    if (!startTimestamp) startTimestamp = timestamp;
    const progress = Math.min((timestamp - startTimestamp) / duration, 1);
    element.innerText = Math.floor(progress * (end - start) + start).toLocaleString();
    if (progress < 1) {
      window.requestAnimationFrame(step);
    }
  };
  window.requestAnimationFrame(step);
}

let lastAbsoluteReadyTotal = 0
let lastAbsoluteInProgressTotal = 0
let lastAbsoluteDoneTotal = 0
let lastAbsoluteBacklogTotal = 0

async function updateAbsoluteStats() {
  try {
    const response = await fetch(`${API_PREFIX}api/dashboard_stats_absolute`);
    if (!response.ok) {
      throw new Error(`API request failed with status ${response.status}`);
    }
    const stats = await response.json();
    const readyTotalEl = document.getElementById("ready-total");
    const inProgressTotalEl = document.getElementById("in-progress-total");
    const doneTotalEl = document.getElementById("done-total");
    const backlogTotalEl = document.getElementById("backlog-total");

    animateValue(readyTotalEl, lastAbsoluteReadyTotal, stats.ReadyTotal, 1500);
    animateValue(inProgressTotalEl, lastAbsoluteInProgressTotal, stats.InProgressTotal, 1500);
    animateValue(doneTotalEl, lastAbsoluteDoneTotal, stats.DoneTotal, 1500);
    animateValue(backlogTotalEl, lastAbsoluteBacklogTotal, stats.BacklogTotal, 1500);

    lastAbsoluteReadyTotal = stats.ReadyTotal
    lastAbsoluteInProgressTotal = stats.InProgressTotal
    lastAbsoluteDoneTotal = stats.DoneTotal
    lastAbsoluteBacklogTotal = stats.BacklogTotal

  } catch (error) {
    console.error("Failed to update stats:", error);
    document.getElementById('ready-total').textContent = 'Error';
  }
};

document.addEventListener('DOMContentLoaded', () => {
  updateRecentActivity();
  updateAbsoluteStats();
  updateDocumentPreviewStats();

  const animatedElements = document.querySelectorAll(".animate-on-load");
  animatedElements.forEach(el => {
    const delay = el.style.getPropertyValue("--delay") || "0ms";
    setTimeout(() => {
      el.classList.remove("opacity-0", "translate-y-4");
    }, parseInt(delay));
  });
});

setInterval(updateRecentActivity, 15000);
setInterval(updateDocumentPreviewStats(''), 15000);
setInterval(updateAbsoluteStats, 15000);
