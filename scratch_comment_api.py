import sys

file_path = 'd:/Interview AI new phrase/app/main.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_change_setup = False
in_confirm_start = False
in_launch_confirm = False

for i, line in enumerate(lines):
    # Detect start of change_interview_setup
    if line.startswith('@app.post("/interview/change-setup"'):
        in_change_setup = True
        
    # Detect end of change_interview_setup
    if in_change_setup and i > 1180 and line.strip() == 'raise HTTPException(status_code=500, detail=str(e))':
        new_lines.append('# ' + line)
        in_change_setup = False
        continue

    # Detect start of confirm_start
    if line.startswith('@app.post("/api/interview/confirm-start"'):
        in_confirm_start = True
        
    # Detect end of confirm_start
    if in_confirm_start and i > 1620 and line.strip() == '}':
        new_lines.append('# ' + line)
        in_confirm_start = False
        continue

    # Detect call to confirm_start in launch_and_confirm_interview
    if line.strip() == '# 4. Call the existing confirm-start logic internally':
        in_launch_confirm = True

    if in_launch_confirm and line.strip() == 'except Exception as e:':
        new_lines.append('# ' + line)
        continue
    if in_launch_confirm and line.strip() == 'raise HTTPException(status_code=500, detail="Failed to generate interview questions")':
        new_lines.append('# ' + line)
        in_launch_confirm = False
        continue

    if in_change_setup or in_confirm_start or in_launch_confirm:
        new_lines.append('# ' + line)
    else:
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Done!')
