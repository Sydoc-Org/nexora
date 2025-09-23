const API_PREFIX = window.location.href.includes("sydocportal") ? "/sydocportal/" : "/";

async function populateKpiCards() {
  try {
    const response = await fetch(`${API_PREFIX}api/reports/kpi_stats`);
    if (!response.ok) throw new Error('Failed to fetch KPI data');
    const stats = await response.json();

    document.getElementById('kpi-processed-today').textContent = stats.processed_today.toLocaleString();
    document.getElementById('kpi-processed-week').textContent = stats.processed_week.toLocaleString();
    document.getElementById('kpi-current-backlog').textContent = stats.current_backlog.toLocaleString();

  } catch (error) {
    console.error("Error populating KPI cards:", error);
    document.getElementById('kpi-processed-today').textContent = 'Error';
    document.getElementById('kpi-processed-week').textContent = 'Error';
    document.getElementById('kpi-current-backlog').textContent = 'Error';
  }
}

async function renderProcessedOverTimeChart() {
  try {
    const response = await fetch(`${API_PREFIX}api/reports/processed_over_time`);
    if (!response.ok) throw new Error('Failed to fetch processed over time data');
    const chartData = await response.json();

    const ctx = document.getElementById('processedOverTimeChart').getContext('2d');
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: chartData.labels,
        datasets: [{
          label: 'Workitems Processed',
          data: chartData.data,
          borderColor: 'rgb(79, 70, 229)',
          backgroundColor: 'rgba(79, 70, 229, 0.1)',
          fill: true,
          tension: 0.4,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true } },
        plugins: { legend: { display: false } }
      }
    });
  } catch (error) {
    console.error("Error rendering processed over time chart:", error);
    document.getElementById('processedOverTimeChart').parentElement.innerHTML =
      '<p class="text-red-500">Could not load chart data.</p>';
  }
}

async function renderStatusDistributionChart() {
  try {
    const response = await fetch(`${API_PREFIX}api/reports/status_distribution`);
    if (!response.ok) throw new Error('Failed to fetch status distribution data');
    const chartData = await response.json();

    const ctx = document.getElementById('statusDistributionChart').getContext('2d');
    new Chart(ctx, {
      type: 'pie',
      data: {
        labels: chartData.labels,
        datasets: [{
          data: chartData.data,
          backgroundColor: ['rgb(59, 130, 246)', 'rgb(251, 191, 36)', 'rgb(34, 197, 94)', 'rgb(168, 85, 247)'],
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: { legend: { position: 'top' } }
      }
    });
  } catch (error) {
    console.error("Error rendering status distribution chart:", error);
    document.getElementById('statusDistributionChart').parentElement.innerHTML =
      '<p class="text-red-500">Could not load chart data.</p>';
  }
}


async function renderStageBreakdownChart() {
  try {
    const response = await fetch(`${API_PREFIX}api/reports/stage_breakdown`);
    if (!response.ok) throw new Error('Failed to fetch stage breakdown data');
    const chartData = await response.json();

    const ctx = document.getElementById('stageBreakdownChart').getContext('2d');
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: chartData.labels,
        datasets: [{
          label: 'Number of Items',
          data: chartData.data,
          backgroundColor: 'rgba(234, 88, 12, 0.8)',
          borderColor: 'rgb(234, 88, 12)',
          borderWidth: 1
        }]
      },
      options: {
        indexAxis: 'y', 
        responsive: true,
        maintainAspectRatio: true,
        scales: { x: { beginAtZero: true } },
        plugins: { legend: { display: false } }
      }
    });
  } catch (error) {
    console.error("Error rendering stage breakdown chart:", error);
    document.getElementById('stageBreakdownChart').parentElement.innerHTML =
      '<p class="text-red-500">Could not load chart data.</p>';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  populateKpiCards();
  renderProcessedOverTimeChart();
  renderStatusDistributionChart();
  renderStageBreakdownChart();
});