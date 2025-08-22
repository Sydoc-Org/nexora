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

const supportLink = document.querySelector(".support-link");

supportLink.addEventListener("click", function () {
  logAction("click_support_link");
});

document.addEventListener("DOMContentLoaded", function () {
  const list = document.getElementById("recent-activity-list");
  list.innerHTML = '<li class="text-gray-500">Loading...</li>';

  fetch("/recent_activity")
    .then((response) => {
      if (!response.ok) {
        throw new Error("Nicht eingeloggt oder Fehler beim Abrufen");
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
          textMessage = `Workitem <span class="font-bold">${activity.fileid}</span> is ready`;
        } else if (status === "In Progress") {
          iconHTML = `
                        <div class="h-6 w-6 flex-shrink-0 bg-yellow-100 text-yellow-600 flex items-center justify-center rounded-full mr-3 mt-1">
                            <i class="fa-solid fa-spinner text-xs"></i>
                        </div>
                    `;
          textMessage = `Processing for Workitem <span class="font-bold">${activity.fileid}</span> has started.`;
        } else if (status === "Done") {
          iconHTML = `
                        <div class="h-6 w-6 flex-shrink-0 bg-indigo-100 text-indigo-600 flex items-center justify-center rounded-full mr-3 mt-1">
                            <i class="fas fa-file-upload text-xs"></i>
                        </div>
                    `;
          textMessage = `Workitem <span class="font-bold">${activity.fileid}</span> has finished processing.`;
        } else if (status === "Collected") {
          iconHTML = `
                        <div class="h-6 w-6 flex-shrink-0 bg-green-100 text-green-600 flex items-center justify-center rounded-full mr-3 mt-1">
                            <i class="fas fa-check text-xs"></i>
                        </div>
                    `;
          textMessage = `Workitem <span class="font-bold">${activity.fileid}</span> was just collected.`;
        } else {
          iconHTML = `
                        <div class="h-6 w-6 flex-shrink-0 bg-gray-300 text-gray-700 flex items-center justify-center rounded-full mr-3 mt-1">
                            <i class="fas fa-question text-xs"></i>
                        </div>
                    `;
          textMessage = `Unknown status for Workitem <span class="font-bold">${activity.fileid}</span>.`;
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
      console.error("Fehler beim Laden der Aktivitäten:", error);
      list.innerHTML =
        '<li class="text-red-500">Fehler beim Laden der Aktivitäten.</li>';
    });
});
