const API_PREFIX = window.location.href.includes("sydocportal") ? "/sydocportal/" : "/";
let animationTimeouts = [];

function cancelAllAnimations() {
  animationTimeouts.forEach(clearTimeout);
  animationTimeouts = []; 

  const allRows = document.querySelectorAll('#workitemsTable tbody tr.workitem-row');
  allRows.forEach(row => {
    row.classList.remove('opacity-0');
    row.style.transform = ''; 
  });
}

function logAction(actionType, resourceId = null, details = null) {
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

// Search functionality
document.getElementById("searchInput").addEventListener("keyup", function () {
  closeAllDetails();
  cancelAllAnimations();
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

document.getElementById("statusFilter").addEventListener("change", function () {
  closeAllDetails();
  cancelAllAnimations();
  const selectedStatus = this.value;
  const allRows = document.querySelectorAll(".workitem-row");
  let visibleCount = 0;

  logAction("filter_workitemList", null, { by_status: selectedStatus });

  allRows.forEach(row => {
    const rowStatus = row.dataset.status;
    
    if (!selectedStatus || rowStatus === selectedStatus) {
      row.classList.remove('hidden');
      visibleCount++;
    } else {
      row.classList.add('hidden');
    }
  });
  
  document.getElementById("showingCount").textContent = visibleCount;
});

function closeAllDetails() {
  document.querySelectorAll("[id^='details-row-']").forEach((detailsRow) => {
    detailsRow.classList.remove('open');
    detailsRow.setAttribute('hidden', true); 
  });

  document.querySelectorAll(".indicator").forEach((chevron) => {
    chevron.classList.remove('open');
    chevron.classList.remove('glyphicon-chevron-down-custom');
    chevron.classList.add('glyphicon-chevron-up-custom');
  });
}

function sortTable(columnIndex) {
  const table = document.getElementById("workitemsTable");
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);

  const workitemRows = Array.from(tbody.querySelectorAll(".workitem-row"));

  workitemRows.sort((a, b) => {
    const aValue = a.cells[columnIndex].textContent.trim();
    const bValue = b.cells[columnIndex].textContent.trim();

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

// Export to CSV functionality
function exportToCSV() {
  logAction("CSVexport_workitemList", null, {
    searchInput: getCurrentFilterOrSearch().search || "none",
    filteredFor: getCurrentFilterOrSearch().status || "All",
  });
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

function getCurrentFilterOrSearch() {
  const statusFilter = document.getElementById("statusFilter");
  const searchInput = document.getElementById("searchInput");
  return {
    status: statusFilter.value,
    search: searchInput.value,
  };
}

async function loadHistory(workitemId) {
  const historyContainer = document.getElementById(`history-container-${workitemId}`);
  if (!historyContainer) {
    console.error(`History container not found for workitem ID: ${workitemId}`);
    return;
  }

  if (historyContainer.dataset.loaded === 'true') {
    return;
  }

  try {
    const response = await fetch(`${API_PREFIX}api/get_audithistory/${workitemId}`);
    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }
    const historyData = await response.json();

    historyContainer.innerHTML = '';

    if (historyData.length === 0) {
      historyContainer.innerHTML = `<p class="text-gray-500">No history available for this item</p>`;
    } else {
      const timeline = document.createElement('div');
      timeline.className = 'border-l-2 border-indigo-200 ml-2';

      historyData.forEach(item => {
        const eventElement = document.createElement('div');
        eventElement.className = 'relative mb-4 pl-6';

        const dot = document.createElement('div');
        dot.className = 'absolute -left-[7px] top-1 h-3 w-3 rounded-full bg-indigo-500';
        eventElement.appendChild(dot);

        const eventText = document.createElement('p');
        eventText.className = 'text-sm text-gray-800';
        eventText.innerHTML = `<strong class="font-semibold">${item.Step}:</strong> ${item.Activity}`;
        eventElement.appendChild(eventText);

        const detailsText = document.createElement('p');
        detailsText.className = 'text-xs text-gray-500 mt-1';
        const eventDate = new Date(item.DateTime);
        const formattedDate = eventDate.toLocaleString(undefined, {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit'
        });
        detailsText.textContent = formattedDate;
        eventElement.appendChild(detailsText);

        timeline.appendChild(eventElement);
      });
      historyContainer.appendChild(timeline);
    }

    historyContainer.dataset.loaded = 'true';

  } catch (error) {
    console.error('Failed to load history:', error);
    historyContainer.innerHTML = `<p class="text-red-500">Could not load history</p>`;
  }
}

async function toggleDetailsAndLoadImages(event) {
  const button = event.currentTarget;
  const workitemid = button.dataset.workitemid;
  const detailsRow = document.getElementById(`details-row-${workitemid}`);
  const imageContainer = document.getElementById(`image-container-${workitemid}`);
  const chevron = button.querySelector('.indicator');

  if (!detailsRow || !imageContainer) {
    console.error('Could not find detail elements for workitem:', workitemid);
    return;
  }

  const isHidden = detailsRow.hasAttribute('hidden');
  if (isHidden) {
    detailsRow.removeAttribute('hidden');
    setTimeout(() => {
      detailsRow.classList.add('open');
      chevron.classList.add('open');
    }, 10);
  } else {
    detailsRow.classList.remove('open');
    chevron.classList.remove('open');
    detailsRow.addEventListener('transitionend', () => {
      detailsRow.hidden = true;
    }, { once: true });
  }

  chevron.classList.toggle('glyphicon-chevron-up-custom');
  chevron.classList.toggle('glyphicon-chevron-down-custom');

  if (!isHidden) {
    return;
  }

  const isLoaded = imageContainer.dataset.loaded === 'true';
  if (isLoaded) {
    return;
  }

  imageContainer.innerHTML = '<p class="text-gray-500 animate-pulse">Checking for media...</p>';
  try {
    loadHistory(workitemid); 
    const infoResponse = await fetch(`${API_PREFIX}api/get_media_info/${workitemid}`);
    if (!infoResponse.ok) {
      throw new Error('Could not fetch media information.');
    }
    const mediaInfo = await infoResponse.json();
    const imageCount = mediaInfo.media_count;

    imageContainer.dataset.loaded = 'true';

    if (imageCount === 0) {
      imageContainer.innerHTML = '<p class="text-gray-500">No media found for this workitem.</p>';
      return;
    }

    imageContainer.innerHTML = '';
    imageContainer.classList.remove('justify-center', 'items-center');
    imageContainer.classList.add('flex-wrap', 'gap-4', 'justify-start'); 

    const imagePromises = [];
    for (let i = 0; i < imageCount; i++) {
      imagePromises.push(loadImage(imageContainer, workitemid, i));
    }

  } catch (error) {
    console.error('Error loading media info:', error);
    imageContainer.innerHTML = `<p class="text-red-500">Could not load media. ${error.message}</p>`;
    imageContainer.dataset.loaded = 'true';
  }
}

async function loadImage(container, workitemid, index) {
  const placeholder = document.createElement('div');
  placeholder.className = 'flex justify-center items-center w-40 h-40 bg-gray-200 rounded animate-pulse';
  container.appendChild(placeholder);

  try {
    const apiUrl = `${API_PREFIX}api/get_media_raw/${workitemid}/${index}`;
    const response = await fetch(apiUrl);

    if (!response.ok) {
      throw new Error(`Status ${response.status}`);
    }

    const imageBlob = await response.blob();
    const imageUrl = URL.createObjectURL(imageBlob);

    const imgElement = document.createElement('img');
    imgElement.src = imageUrl;
    imgElement.alt = `Media ${index + 1} for workitem ${workitemid}`;
    imgElement.className = 'w-40 h-40 object-cover rounded shadow-lg workitem-image';

    imgElement.onload = () => {
      URL.revokeObjectURL(imageUrl);
      placeholder.replaceWith(imgElement);
    };
    imgElement.onerror = () => {
      throw new Error('Image could not be loaded into element.');
    }

  } catch (error) {
    console.error(`Error loading image index ${index}:`, error);
    placeholder.innerHTML = `<div class="text-center text-xs text-red-600 p-2">Failed to load image ${index + 1}</div>`;
    placeholder.classList.remove('animate-pulse', 'bg-gray-200');
    placeholder.classList.add('bg-red-100', 'border', 'border-red-400');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById("imageModal");
  const modalImg = document.getElementById("modalImage");
  const closeBtn = document.querySelector(".modal-close");

  document.addEventListener('click', function (event) {
    if (event.target && event.target.classList.contains('workitem-image')) {
      modal.style.display = "flex";
      modalImg.src = event.target.src;
    }
  });

  function closeModal() {
    modal.style.display = "none";
  }

  closeBtn.addEventListener('click', closeModal);

  modal.addEventListener('click', function (event) {
    if (event.target === modal) {
      closeModal();
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && modal.style.display === "flex") {
      closeModal();
    }
  });
  const detailButtons = document.querySelectorAll('.details-toggle-button');
  detailButtons.forEach(button => {
    button.addEventListener('click', toggleDetailsAndLoadImages);
  });

  const animatedElements = document.querySelectorAll('.animate-on-load');
  animatedElements.forEach(el => {
    const delay = el.style.getPropertyValue('--delay') || '0ms';
    setTimeout(() => {
      el.classList.remove('opacity-0', 'translate-y-4');
    }, parseInt(delay));
  });

  const tableRows = document.querySelectorAll('#workitemsTable tbody tr.workitem-row');
  tableRows.forEach(row => {
    const delay = row.style.getPropertyValue('--delay') || '0ms';
    const timeoutId = setTimeout(() => {
      row.style.transform = 'translateX(-15px)';
      row.classList.remove('opacity-0');
      setTimeout(() => {
        row.style.transform = 'translateX(0)';
      }, 10);
    }, 200 + parseInt(delay));
    animationTimeouts.push(timeoutId); 
  });
});