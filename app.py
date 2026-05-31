import datetime
import json
from flask import Flask, render_template, request, jsonify
import plotly.graph_objects as go
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder

from metrics_reader import MetricsReader

app = Flask(__name__)
reader = MetricsReader("metrics.jsonl")

# Sleek premium dark mode theme color palette
THEME_COLORS = {
    "system_cpu": "#06B6D4",      # Bright Cyan
    "system_ram": "#3B82F6",      # Vivid Blue
    "target_proc": "#8B5CF6",     # Electric Violet
    "residual_cpu": "#EF4444",    # Warning Coral/Red
    "other_proc": ["#F59E0B", "#10B981", "#EC4899", "#6366F1", "#14B8A6"] # Amber, Emerald, Pink, Indigo, Teal
}

def apply_plotly_dark_theme(layout):
    """Applies a consistent dark-theme template to a Plotly layout."""
    layout.update(
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        font=dict(
            family="Outfit, Inter, sans-serif",
            color="#E2E8F0"
        ),
        margin=dict(l=50, r=30, t=50, b=50),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#1E293B",
            font_size=12,
            font_family="Outfit, Inter, sans-serif"
        ),
        xaxis=dict(
            gridcolor="#1E293B",
            linecolor="#334155",
            tickfont=dict(color="#94A3B8"),
            title=dict(font=dict(color="#94A3B8"))
        ),
        yaxis=dict(
            gridcolor="#1E293B",
            linecolor="#334155",
            tickfont=dict(color="#94A3B8"),
            title=dict(font=dict(color="#94A3B8"))
        )
    )
    return layout

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/metadata")
def get_metadata():
    metadata = reader.get_metadata()
    return jsonify(metadata)

@app.route("/api/metrics")
def get_metrics():
    # 1. Parse parameters
    time_range = request.args.get("range", "7d")  # 24h, 7d, 30d, all
    granularity = request.args.get("granularity", "day")  # hour, day, month, year
    target_process = request.args.get("target_process", "simulation_engine.exe")

    # 2. Determine time window
    now = datetime.datetime.now(datetime.timezone.utc)
    start_time = None
    if time_range == "24h":
        start_time = now - datetime.timedelta(hours=24)
    elif time_range == "7d":
        start_time = now - datetime.timedelta(days=7)
    elif time_range == "30d":
        start_time = now - datetime.timedelta(days=30)
        
    # For simulation purposes, since our mock data stops at the current generation time,
    # let's just parse the full or filtered range
    
    # 3. Read and aggregate data
    mach_data, proc_data, process_names = reader.get_aggregated_metrics(
        start_time=start_time,
        end_time=now,
        granularity=granularity,
        target_process=target_process
    )
    
    if not mach_data or "timestamp" not in mach_data or not mach_data["timestamp"]:
        return jsonify({
            "error": "No data found for the selected timeframe. Try a different range or regenerate data."
        }), 404

    # 4. Generate Plotly figures in Python
    timestamps = mach_data["timestamp"]
    
    # --- CHART 1: System-wide CPU and RAM Utilization ---
    fig_system = go.Figure()
    fig_system.add_trace(go.Scatter(
        x=timestamps,
        y=mach_data["cpu_util_percent"],
        name="System CPU %",
        line=dict(color=THEME_COLORS["system_cpu"], width=2.5),
        mode='lines'
    ))
    fig_system.add_trace(go.Scatter(
        x=timestamps,
        y=mach_data["ram_util_percent"],
        name="System RAM %",
        line=dict(color=THEME_COLORS["system_ram"], width=2.5),
        mode='lines'
    ))
    fig_system.update_layout(
        title="Overall System Resource Utilization",
        yaxis_title="Utilization (%)",
        yaxis=dict(range=[0, 100])
    )
    apply_plotly_dark_theme(fig_system.layout)
    
    # --- CHART 2: Contention Analysis (Target vs residual CPU) ---
    # Residual CPU is total CPU - target process CPU. If residual is high, other apps are hogging resource.
    fig_contention = go.Figure()
    
    target_cpu = [0.0] * len(timestamps)
    target_ram = [0.0] * len(timestamps)
    if target_process in proc_data:
        # Align target process metrics by timestamps
        target_dict = proc_data[target_process]
        # In case lengths match exactly (they should due to resampling)
        if len(target_dict["cpu_percent"]) == len(timestamps):
            target_cpu = target_dict["cpu_percent"]
            target_ram = target_dict["memory_percent"]
            
    # Calculate Residual CPU (System CPU - Target Process CPU)
    residual_cpu = []
    for sys_cpu, tg_cpu in zip(mach_data["cpu_util_percent"], target_cpu):
        residual_cpu.append(max(0.0, sys_cpu - tg_cpu))
        
    fig_contention.add_trace(go.Scatter(
        x=timestamps,
        y=target_cpu,
        name=f"{target_process} CPU %",
        line=dict(color=THEME_COLORS["target_proc"], width=3),
        fill='tozeroy',
        fillcolor='rgba(139, 92, 246, 0.1)', # Translucent violet
        mode='lines'
    ))
    
    fig_contention.add_trace(go.Scatter(
        x=timestamps,
        y=residual_cpu,
        name="Other Processes CPU % (Residual)",
        line=dict(color=THEME_COLORS["residual_cpu"], width=2, dash='dash'),
        fill='tonexty',
        fillcolor='rgba(239, 68, 68, 0.05)', # Translucent coral
        mode='lines'
    ))
    
    fig_contention.add_trace(go.Scatter(
        x=timestamps,
        y=mach_data["cpu_util_percent"],
        name="Total System CPU %",
        line=dict(color="rgba(226, 232, 240, 0.4)", width=1.5),
        mode='lines'
    ))
    
    fig_contention.update_layout(
        title=f"Resource Contention Analysis: {target_process} vs. Others",
        yaxis_title="CPU Utilization (%)",
        yaxis=dict(range=[0, 100])
    )
    apply_plotly_dark_theme(fig_contention.layout)
    
    # --- CHART 3: Top Processes Over Time ---
    # Stacked area chart showing how top processes share the CPU load
    fig_procs = go.Figure()
    
    color_index = 0
    for proc_name, proc_metrics in proc_data.items():
        if proc_name == target_process:
            color = THEME_COLORS["target_proc"]
        else:
            color = THEME_COLORS["other_proc"][color_index % len(THEME_COLORS["other_proc"])]
            color_index += 1
            
        fig_procs.add_trace(go.Scatter(
            x=timestamps,
            y=proc_metrics["cpu_percent"],
            name=proc_name,
            stackgroup='one', # stack them together!
            line=dict(width=1),
            fillcolor=color.replace("#", "rgba(") + ", 0.45)" if "#" in color else color # trans
        ))
        
    fig_procs.update_layout(
        title="Top Resource-Consuming Processes CPU Share",
        yaxis_title="Stacked CPU Utilization (%)",
        yaxis=dict(range=[0, 100])
    )
    apply_plotly_dark_theme(fig_procs.layout)
    
    # 5. Serialize Plotly figures to JSON using Encoder
    return json.dumps({
        "system_chart": json.loads(json.dumps(fig_system, cls=PlotlyJSONEncoder)),
        "contention_chart": json.loads(json.dumps(fig_contention, cls=PlotlyJSONEncoder)),
        "procs_chart": json.loads(json.dumps(fig_procs, cls=PlotlyJSONEncoder)),
        "process_names": process_names,
        "selected_target": target_process,
        "averages": {
            "sys_cpu": round(sum(mach_data["cpu_util_percent"]) / len(mach_data["cpu_util_percent"]), 1),
            "sys_ram": round(sum(mach_data["ram_util_percent"]) / len(mach_data["ram_util_percent"]), 1),
            "target_cpu": round(sum(target_cpu) / len(target_cpu), 1),
            "target_ram": round(sum(target_ram) / len(target_ram), 1)
        }
    })

if __name__ == "__main__":
    # Ensure templates directory exists before running
    import os
    os.makedirs("templates", exist_ok=True)
    app.run(debug=True, host="127.0.0.1", port=5000)
