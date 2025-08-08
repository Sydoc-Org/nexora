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

  rows.sort((a, b) => {
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
function viewDetails(workitemId) {
  //placeholder: open card with details in this function
}

// Export to CSV functionality
function exportToCSV() {
  let csv = [];
  const table = document.getElementById("workitemsTable");
  const rows = table.querySelectorAll('tr:not([style*="display: none"])');

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
