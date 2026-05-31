import json
import datetime
import random
import os

def generate_data(filepath="metrics.jsonl", days=14, interval_minutes=15):
    print(f"Generating mock metrics data for {days} days every {interval_minutes} minutes...")
    
    # Base configuration
    machine_config = {
        "hostname": "KLA-SYS-PERF03",
        "cpu_count": 16,
        "total_ram_gb": 64.0,
        "os": "Windows 11 Enterprise (23H2)"
    }
    
    start_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    total_steps = int((days * 24 * 60) / interval_minutes)
    
    with open(filepath, "w") as f:
        for step in range(total_steps):
            current_time = start_time + datetime.timedelta(minutes=step * interval_minutes)
            hour = current_time.hour
            weekday = current_time.weekday()
            
            # 1. Base System Metric Generation (oscillates slightly by time of day)
            is_work_hour = 9 <= hour < 18 and weekday < 5
            base_cpu = 15.0 + (15.0 * random.random()) if is_work_hour else 5.0 + (8.0 * random.random())
            base_ram = 25.0 + (10.0 * random.random()) # base OS + system cache
            
            # Define running processes and their resource consumption
            processes_data = []
            
            # --- PROCESS A: Target App (simulation_engine.exe) ---
            # It runs workload cycles: busy for ~3 periods, then idle for 1 period.
            cycle_phase = (step // 4) % 4
            is_target_active = cycle_phase < 3
            if is_target_active:
                target_cpu = 30.0 + random.uniform(-5.0, 5.0)
                target_ram = 15.0 + random.uniform(-1.0, 1.0)
            else:
                target_cpu = 1.0 + random.uniform(0.0, 1.5)
                target_ram = 12.0 + random.uniform(-0.5, 0.5)
            
            # --- PROCESS B: Antivirus (antivirus_scan.exe) ---
            # Runs a heavy daily scan at 2 AM to 3:30 AM
            is_av_running = (hour == 2 and current_time.minute >= 0) or (hour == 3 and current_time.minute < 30)
            if is_av_running:
                av_cpu = 50.0 + random.uniform(-5.0, 10.0)
                av_ram = 18.0 + random.uniform(-0.5, 2.0)
            else:
                av_cpu = 0.5 + random.uniform(0.0, 0.5)
                av_ram = 2.0 + random.uniform(-0.1, 0.1)
                
            # --- PROCESS C: Compile Job (compile_job.exe) ---
            # Runs randomly during work hours for short bursts
            # Simulates sudden heavy contention
            is_compiling = is_work_hour and (random.random() < 0.08) # 8% chance per 15 mins during work hours
            if is_compiling:
                compile_cpu = 65.0 + random.uniform(-10.0, 10.0)
                compile_ram = 12.0 + random.uniform(-1.0, 3.0)
            else:
                compile_cpu = 0.0
                compile_ram = 0.0
                
            # --- PROCESS D: Web Browser (chrome.exe) ---
            # Steady medium RAM usage, higher during work hours
            chrome_cpu = random.uniform(1.0, 8.0) if is_work_hour else random.uniform(0.1, 2.0)
            chrome_ram = random.uniform(8.0, 14.0) if is_work_hour else random.uniform(4.0, 6.0)
            
            # --- PROCESS E: SQL Database (sqlserver.exe) ---
            # Steady base load
            sql_cpu = random.uniform(3.0, 7.0) if is_work_hour else random.uniform(1.0, 3.0)
            sql_ram = 8.0 + random.uniform(-0.5, 0.5)

            # Build list of active processes
            processes_data.append({"pid": 5412, "name": "simulation_engine.exe", "cpu_percent": round(target_cpu, 2), "memory_percent": round(target_ram, 2)})
            processes_data.append({"pid": 1102, "name": "antivirus_scan.exe", "cpu_percent": round(av_cpu, 2), "memory_percent": round(av_ram, 2)})
            if compile_cpu > 0:
                processes_data.append({"pid": 9120, "name": "compile_job.exe", "cpu_percent": round(compile_cpu, 2), "memory_percent": round(compile_ram, 2)})
            processes_data.append({"pid": 8832, "name": "chrome.exe", "cpu_percent": round(chrome_cpu, 2), "memory_percent": round(chrome_ram, 2)})
            processes_data.append({"pid": 3216, "name": "sqlserver.exe", "cpu_percent": round(sql_cpu, 2), "memory_percent": round(sql_ram, 2)})
            
            # Sum up CPU/RAM for the system
            # Combine base OS utilization + running processes
            sum_proc_cpu = sum(p["cpu_percent"] for p in processes_data)
            sum_proc_ram = sum(p["memory_percent"] for p in processes_data)
            
            total_cpu = min(98.5, base_cpu + sum_proc_cpu) # cap slightly under 100
            total_ram = min(95.0, base_ram + sum_proc_ram) # cap RAM
            
            # Disk IO and Network metrics (simulated)
            disk_read = 50000.0 * (target_cpu + av_cpu)
            disk_write = 20000.0 * (target_cpu + compile_cpu)
            net_sent = 5000.0 * sql_cpu
            net_recv = 10000.0 * chrome_cpu
            
            # Record dictionary
            record = {
                "timestamp": current_time.isoformat(),
                "machine_data": machine_config,
                "machine_metrics": {
                    "cpu_util_percent": round(total_cpu, 2),
                    "ram_util_percent": round(total_ram, 2),
                    "disk_read_bytes_sec": round(disk_read, 2),
                    "disk_write_bytes_sec": round(disk_write, 2),
                    "network_sent_bytes_sec": round(net_sent, 2),
                    "network_recv_bytes_sec": round(net_recv, 2)
                },
                "processes": processes_data
            }
            
            f.write(json.dumps(record) + "\n")
            
    print(f"Successfully generated {total_steps} metrics lines in '{filepath}'.")

if __name__ == "__main__":
    generate_data("metrics.jsonl", days=14)
