import urllib.request, json
url = 'https://api.github.com/repos/qingxuandaoming/Picture/actions/runs'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    resp = urllib.request.urlopen(req).read().decode('utf-8')
    data = json.loads(resp)
    if data['workflow_runs']:
        run_id = data['workflow_runs'][0]['id']
        jobs_url = f'https://api.github.com/repos/qingxuandaoming/Picture/actions/runs/{run_id}/jobs'
        jobs_resp = urllib.request.urlopen(urllib.request.Request(jobs_url, headers={'User-Agent': 'Mozilla/5.0'})).read().decode('utf-8')
        jobs_data = json.loads(jobs_resp)
        for job in jobs_data['jobs']:
            print(f"Job: {job['name']}, Conclusion: {job['conclusion']}")
            for step in job['steps']:
                if step['conclusion'] == 'failure':
                    print(f"  Failed step: {step['name']}")
                    
        # Also get logs for the failed job
        for job in jobs_data['jobs']:
            if job['conclusion'] == 'failure':
                log_url = f"https://api.github.com/repos/qingxuandaoming/Picture/actions/jobs/{job['id']}/logs"
                try:
                    log_resp = urllib.request.urlopen(urllib.request.Request(log_url, headers={'User-Agent': 'Mozilla/5.0'})).read().decode('utf-8')
                    print(f"\n--- Logs for {job['name']} ---\n")
                    print("\n".join(log_resp.split("\n")[-50:]))
                except Exception as e:
                    print(f"Could not fetch logs for {job['name']}: {e}")
except Exception as e:
    print(f"Error: {e}")
