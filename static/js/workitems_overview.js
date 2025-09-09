function logAction(actionType, resourceId = null, details = null) {
  // fetch("/sydocportal/log_action", {
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

  logAction("filter_workitemList", null, { by_status: selectedStatus });

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

document.addEventListener('DOMContentLoaded', () => {
  const detailButtons = document.querySelectorAll('.details-toggle-button');
  detailButtons.forEach(button => {
    button.addEventListener('click', toggleDetailsAndLoadImages); 
  });
});

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
    chevron.classList.remove('glyphicon-chevron-up-custom');
    chevron.classList.add('glyphicon-chevron-down-custom');
  } else {
    detailsRow.setAttribute('hidden', true);
    chevron.classList.remove('glyphicon-chevron-down-custom');
    chevron.classList.add('glyphicon-chevron-up-custom');
    return;
  }

  const isLoaded = imageContainer.dataset.loaded === 'true';
  if (isLoaded) {
    return; 
  }
  
  imageContainer.innerHTML = '<p class="text-gray-500 animate-pulse">Checking for media...</p>';

  try {
    // const infoResponse = await fetch(`/sydocportal/api/get_media_info/${workitemid}`);
    const infoResponse = await fetch(`/api/get_media_info/${workitemid}`);
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
    imageContainer.style.display = 'flex';
    imageContainer.style.flexWrap = 'wrap';
    imageContainer.style.gap = '1rem'; 

    for (let i = 0; i < imageCount; i++) {
        loadImage(imageContainer, workitemid, i);
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
    //const apiUrl = `/sydocportal/api/get_media_raw/${workitemid}/${index}`;
    const apiUrl = `/api/get_media_raw/${workitemid}/${index}`;
    const response = await fetch(apiUrl);

    if (!response.ok) {
      throw new Error(`Status ${response.status}`);
    }

    const imageBlob = await response.blob();
    const imageUrl = URL.createObjectURL(imageBlob);

    const imgElement = document.createElement('img');
    imgElement.src = imageUrl;
    imgElement.alt = `Media ${index + 1} for workitem ${workitemid}`;
    imgElement.className = 'w-40 h-40 object-cover rounded shadow-lg';
    
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