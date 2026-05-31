import json
import datetime
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional

class MetricsReader:
    def __init__(self, filepath: str = "metrics.jsonl"):
        self.filepath = filepath
        self._metadata = None

    def get_metadata(self) -> Dict[str, Any]:
        """
        Reads the first record in the JSONL file to retrieve static machine configuration metadata.
        Caches it in memory for fast lookup.
        """
        if self._metadata:
            return self._metadata
            
        try:
            with open(self.filepath, 'r') as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        if 'machine_data' in record:
                            self._metadata = record['machine_data']
                            return self._metadata
        except Exception as e:
            print(f"Error reading metadata from '{self.filepath}': {e}")
            
        # Return fallback configuration
        return {
            "hostname": "Unknown-Host",
            "cpu_count": 4,
            "total_ram_gb": 16.0,
            "os": "Unknown OS"
        }

    def read_records_generator(self, start_time: Optional[datetime.datetime] = None, end_time: Optional[datetime.datetime] = None):
        """
        Memory-efficient generator that yields parsed lines from the JSONL file.
        Applies timezone-aware date range filtering during parsing.
        """
        try:
            with open(self.filepath, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                        
                    ts_str = record.get('timestamp')
                    if not ts_str:
                        continue
                    
                    # Convert to datetime and make timezone-aware (UTC)
                    ts = datetime.datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    
                    # Apply time bounds
                    if start_time and ts < start_time:
                        continue
                    if end_time and ts > end_time:
                        continue
                        
                    yield ts, record
        except FileNotFoundError:
            print(f"Metrics file '{self.filepath}' not found.")
            return

    def load_dataframes(self, start_time: Optional[datetime.datetime] = None, end_time: Optional[datetime.datetime] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Reads records from the generator and converts them into two Pandas DataFrames:
        1. df_machine: Contains overall system resource metrics.
        2. df_processes: Contains breakdown of usage per process.
        """
        machine_records = []
        process_records = []
        
        for ts, record in self.read_records_generator(start_time, end_time):
            # 1. Parse Machine Metrics
            mach_metrics = record.get('machine_metrics', {})
            machine_records.append({
                'timestamp': ts,
                'cpu_util_percent': mach_metrics.get('cpu_util_percent', 0.0),
                'ram_util_percent': mach_metrics.get('ram_util_percent', 0.0),
                'disk_read_bytes_sec': mach_metrics.get('disk_read_bytes_sec', 0.0),
                'disk_write_bytes_sec': mach_metrics.get('disk_write_bytes_sec', 0.0),
                'network_sent_bytes_sec': mach_metrics.get('network_sent_bytes_sec', 0.0),
                'network_recv_bytes_sec': mach_metrics.get('network_recv_bytes_sec', 0.0),
            })
            
            # 2. Parse Process Metrics
            for proc in record.get('processes', []):
                process_records.append({
                    'timestamp': ts,
                    'pid': proc.get('pid'),
                    'name': proc.get('name'),
                    'cpu_percent': proc.get('cpu_percent', 0.0),
                    'memory_percent': proc.get('memory_percent', 0.0)
                })
                
        df_mach = pd.DataFrame(machine_records)
        df_proc = pd.DataFrame(process_records)
        
        if not df_mach.empty:
            df_mach.set_index('timestamp', inplace=True)
        if not df_proc.empty:
            df_proc.set_index('timestamp', inplace=True)
            
        return df_mach, df_proc

    def get_aggregated_metrics(self, 
                               start_time: Optional[datetime.datetime] = None, 
                               end_time: Optional[datetime.datetime] = None, 
                               granularity: str = 'day', 
                               target_process: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        """
        Aggregates metrics for system and top processes according to granularity:
        - 'hour' (1h resampling)
        - 'day' (1D resampling)
        - 'month' (1M resampling)
        - 'year' (1Y resampling)
        
        Returns:
            mach_data: Dict of machine timeseries arrays
            proc_data: Dict mapping process name -> timeseries arrays
            process_names: Sorted list of all active process names found in range
        """
        df_mach, df_proc = self.load_dataframes(start_time, end_time)
        
        if df_mach.empty:
            return {}, {}, []
            
        # Resampling rules
        resample_rules = {
            'hour': '1h',
            'day': '1D',
            'month': '1ME',
            'year': '1YE'
        }
        rule = resample_rules.get(granularity.lower(), '1D')
        
        # 1. Aggregate Machine Metrics (mean utilization)
        df_mach_agg = df_mach.resample(rule).mean()
        df_mach_agg.dropna(how='all', inplace=True)
        
        df_mach_agg = df_mach_agg.reset_index()
        # Clean formatting of timestamp for charts
        df_mach_agg['timestamp'] = df_mach_agg['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        mach_data = df_mach_agg.to_dict(orient='list')
        
        # 2. Aggregate Process Metrics
        proc_data = {}
        process_names = []
        
        if not df_proc.empty:
            # Find unique process names in this timeframe
            process_names = sorted(df_proc['name'].unique().tolist())
            
            # Identify target process (fallback to simulation_engine.exe or first one available)
            if not target_process:
                if 'simulation_engine.exe' in process_names:
                    target_process = 'simulation_engine.exe'
                elif len(process_names) > 0:
                    target_process = process_names[0]
            
            # Combine duplicate process names (e.g. Chrome instances) at the same timestamp by summing them
            df_proc_sum = df_proc.groupby(['timestamp', 'name'])[['cpu_percent', 'memory_percent']].sum().reset_index()
            df_proc_sum.set_index('timestamp', inplace=True)
            
            # Find top 4 processes by average CPU usage (so dashboard is uncluttered)
            top_procs = df_proc_sum.groupby('name')['cpu_percent'].mean().sort_values(ascending=False).head(4).index.tolist()
            
            # Always ensure the target process is included in the aggregation list
            procs_to_keep = set(top_procs)
            if target_process:
                procs_to_keep.add(target_process)
                
            agg_list = []
            for proc_name in procs_to_keep:
                df_single = df_proc_sum[df_proc_sum['name'] == proc_name]
                if not df_single.empty:
                    # Resample each process time-series using the same rule
                    df_single_agg = df_single.resample(rule)[['cpu_percent', 'memory_percent']].mean()
                    df_single_agg['name'] = proc_name
                    agg_list.append(df_single_agg)
                    
            if agg_list:
                df_proc_agg = pd.concat(agg_list).reset_index()
                df_proc_agg['timestamp'] = df_proc_agg['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
                
                # Format into dict mapping process name -> lists of values
                for name in df_proc_agg['name'].unique():
                    df_p = df_proc_agg[df_proc_agg['name'] == name]
                    proc_data[name] = df_p.to_dict(orient='list')
                    
        return mach_data, proc_data, process_names
