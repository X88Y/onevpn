import json
import os

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    
    if not os.path.exists(config_path):
        print(f"Error: config.json not found at {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        try:
            configs = json.load(f)
        except Exception as e:
            print(f"Error parsing config.json: {e}")
            return
            
    if not isinstance(configs, list):
        print("Error: config.json root is not a list")
        return

    output_lines = []
    global_unique_ips = set()
    for item in configs:
        remark = item.get("remarks", "").strip()
        outbounds = item.get("outbounds", [])
        
        addresses = []
        for outbound in outbounds:
            settings = outbound.get("settings", {})
            if not settings:
                continue
            
            # Extract from vnext (VLESS/VMess)
            vnext = settings.get("vnext", [])
            for vn in vnext:
                addr = vn.get("address")
                if addr:
                    addresses.append(addr)
                    global_unique_ips.add(addr)
                    
            # Extract from servers (Shadowsocks/Trojan)
            servers = settings.get("servers", [])
            for srv in servers:
                addr = srv.get("address")
                if addr:
                    addresses.append(addr)
                    global_unique_ips.add(addr)
        
        # Deduplicate while preserving order for this remark
        seen = set()
        unique_addresses = []
        for addr in addresses:
            if addr not in seen:
                seen.add(addr)
                unique_addresses.append(addr)
                
        for addr in unique_addresses:
            line = f"{remark} - {addr}"
            print(line)
            output_lines.append(line)

    summary_line = f"Total Unique IPs/Addresses: {len(global_unique_ips)}"
    print(f"\n{summary_line}")
    output_lines.append("")
    output_lines.append(summary_line)

    output_path = os.path.join(script_dir, "output.txt")
    with open(output_path, "w", encoding="utf-8") as out_f:
        out_f.write("\n".join(output_lines) + "\n")
    print(f"Written {len(output_lines)} lines to {output_path}")

if __name__ == "__main__":
    main()
