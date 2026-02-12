/* ============================================================
   Analytics Page JS — Vercel Design
   ============================================================ */

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

document.addEventListener('DOMContentLoaded', () => {
    loadAnalyticsData().catch(console.error);
});

async function loadAnalyticsData() {
    const [activity, summary] = await Promise.all([
        apiFetch('/api/analytics/activity'),
        apiFetch('/api/analytics/summary'),
    ]);

    if (activity) {
        renderHeatmap(activity.heatmap);
        renderHourlyChart(activity.heatmap);
        renderDailyChart(activity.heatmap);
        renderAnalyticsStats(activity, summary);
    }
    if (summary) {
        document.getElementById('analyticsDbSize').textContent = summary.db_size_mb + ' MB';
    }
}

function renderAnalyticsStats(activity, summary) {
    document.getElementById('analyticsTotalEvents').textContent =
        formatNumber(activity.total_events);

    const hourlyTotals = new Array(24).fill(0);
    for (const row of activity.heatmap) {
        for (let h = 0; h < 24; h++) {
            hourlyTotals[h] += row[h];
        }
    }
    const peakHour = hourlyTotals.indexOf(Math.max(...hourlyTotals));
    const ph = peakHour % 12 || 12;
    document.getElementById('analyticsPeakHour').textContent =
        ph + ':00 ' + (peakHour < 12 ? 'AM' : 'PM');

    const dailyTotals = activity.heatmap.map(row => row.reduce((a, b) => a + b, 0));
    const peakDay = dailyTotals.indexOf(Math.max(...dailyTotals));
    document.getElementById('analyticsPeakDay').textContent = DAYS[peakDay];
}

function renderHeatmap(heatmap) {
    const container = document.getElementById('heatmapContainer');

    let maxVal = 1;
    for (const row of heatmap) {
        for (const val of row) {
            if (val > maxVal) maxVal = val;
        }
    }

    let html = '<table class="heatmap-table"><thead><tr><th></th>';
    for (let h = 0; h < 24; h++) {
        const label = h === 0 ? '12a' : h < 12 ? h + 'a' : h === 12 ? '12p' : (h - 12) + 'p';
        html += `<th>${h % 3 === 0 ? label : ''}</th>`;
    }
    html += '</tr></thead><tbody>';

    for (let d = 0; d < 7; d++) {
        html += `<tr><td class="heatmap-day-label">${DAYS[d]}</td>`;
        for (let h = 0; h < 24; h++) {
            const val = heatmap[d][h];
            const intensity = val / maxVal;
            const color = getHeatColor(intensity);
            html += `<td style="background:${color}" title="${DAYS[d]} ${h}:00 — ${val} events"></td>`;
        }
        html += '</tr>';
    }
    html += '</tbody></table>';

    html += '<div style="display:flex;align-items:center;gap:8px;margin-top:16px;justify-content:flex-end;padding:0 16px 16px">';
    html += '<span style="font-size:11px;color:var(--text-tertiary)">Less</span>';
    for (let i = 0; i <= 4; i++) {
        const color = getHeatColor(i / 4);
        html += `<div style="width:16px;height:16px;border-radius:3px;background:${color}"></div>`;
    }
    html += '<span style="font-size:11px;color:var(--text-tertiary)">More</span></div>';

    container.innerHTML = html;
}

function getHeatColor(intensity) {
    if (intensity === 0) return 'rgba(0, 112, 243, 0.04)';
    const alpha = 0.15 + intensity * 0.75;
    return `rgba(0, 112, 243, ${alpha.toFixed(2)})`;
}

let hourlyChart = null;

function renderHourlyChart(heatmap) {
    const canvas = document.getElementById('hourlyChart');
    if (!canvas) return;

    const hourlyTotals = new Array(24).fill(0);
    for (const row of heatmap) {
        for (let h = 0; h < 24; h++) {
            hourlyTotals[h] += row[h];
        }
    }

    const labels = hourlyTotals.map((_, i) => {
        const h = i % 12 || 12;
        return h + (i < 12 ? ' AM' : ' PM');
    });

    const chartData = {
        labels,
        datasets: [{
            label: 'Events',
            data: hourlyTotals,
            backgroundColor: hourlyTotals.map((_, i) => {
                const maxVal = Math.max(...hourlyTotals, 1);
                const intensity = hourlyTotals[i] / maxVal;
                return `rgba(0, 112, 243, ${(0.3 + intensity * 0.6).toFixed(2)})`;
            }),
            borderColor: '#0070F3',
            borderWidth: 1,
            borderRadius: 4,
        }],
    };

    if (hourlyChart) {
        hourlyChart.data = chartData;
        hourlyChart.update();
        return;
    }

    hourlyChart = new Chart(canvas, {
        type: 'bar',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { grid: { display: false } },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255,255,255,0.04)' },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0A0A0A',
                    borderColor: 'rgba(255,255,255,0.08)',
                    borderWidth: 1,
                    titleColor: '#EDEDED',
                    bodyColor: '#888888',
                    padding: 12,
                    cornerRadius: 6,
                },
            },
        },
    });
}

let dailyChart = null;

function renderDailyChart(heatmap) {
    const canvas = document.getElementById('dailyChart');
    if (!canvas) return;

    const dailyTotals = heatmap.map(row => row.reduce((a, b) => a + b, 0));
    const colors = ['#0070F3', '#1A8CFF', '#4DA6FF', '#80BFFF', '#0070F3', '#1A8CFF', '#4DA6FF'];

    const chartData = {
        labels: DAYS,
        datasets: [{
            label: 'Events',
            data: dailyTotals,
            backgroundColor: colors.map(c => c + '99'),
            borderColor: colors,
            borderWidth: 2,
        }],
    };

    if (dailyChart) {
        dailyChart.data = chartData;
        dailyChart.update();
        return;
    }

    dailyChart = new Chart(canvas, {
        type: 'doughnut',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '55%',
            plugins: {
                legend: { position: 'right' },
                tooltip: {
                    backgroundColor: '#0A0A0A',
                    borderColor: 'rgba(255,255,255,0.08)',
                    borderWidth: 1,
                    titleColor: '#EDEDED',
                    bodyColor: '#888888',
                    padding: 12,
                    cornerRadius: 6,
                },
            },
        },
    });
}
