import os, re

frontend_dir = 'frontend/src'
for root, dirs, files in os.walk(frontend_dir):
    for f in files:
        if f.endswith('.vue') or f.endswith('.js') or f.endswith('.ts'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
                imports = re.findall(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]", content)
                for imp in imports:
                    mod = imp[0] or imp[1]
                    target = None
                    if mod.startswith('.'):
                        target = os.path.normpath(os.path.join(root, mod))
                    elif mod.startswith('@/'):
                        target = os.path.normpath(os.path.join('frontend/src', mod[2:]))
                    
                    if target:
                        possible_targets = [target]
                        if not os.path.splitext(target)[1]:
                            possible_targets.extend([target + '.js', target + '.vue', target + '.ts', target + '/index.js', target + '/index.vue'])
                        
                        found = False
                        for pt in possible_targets:
                            if os.path.exists(pt):
                                basename = os.path.basename(pt)
                                parent = os.path.dirname(pt)
                                actual_files = os.listdir(parent)
                                if basename not in actual_files:
                                    print(f"CASE MISMATCH in {path}: {mod} (expected {basename} but real file is something else in {actual_files})")
                                found = True
                                break
                        if not found:
                            print(f"Missing file in {path}: {mod}")
