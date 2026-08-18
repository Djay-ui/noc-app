from PIL import Image, ImageDraw, ImageFont

frames = []
width, height = 800, 300
num_frames = 20

for i in range(num_frames):
    img = Image.new('RGB', (width, height), color='#0b1120')
    draw = ImageDraw.Draw(img)
    
    # Title
    draw.text((250, 20), "NOC APPLICATION WORKFLOW PIPELINE", fill="#38bdf8")
    
    # Nodes
    steps = ["1. Alerts (PRTG)", "2. Ticketing", "3. Shift/Data", "4. ISP Emails"]
    positions = [50, 240, 430, 620]
    
    for idx, (step, x) in enumerate(zip(steps, positions)):
        draw.rectangle([x, 80, x + 130, 220], outline='#1e293b', width=2, fill='#131b2e')
        draw.text((x + 10, 140), step, fill='#f8fafc')
        
        # Draw flow line to next
        if idx < 3:
            next_x = positions[idx+1]
            draw.line([(x + 130, 150), (next_x, 150)], fill='#1e293b', width=3)
            
            # Animated glowing pulse
            pulse_offset = (i * 10) % 60
            pulse_x = x + 130 + pulse_offset
            if pulse_x < next_x:
                draw.ellipse([pulse_x - 4, 146, pulse_x + 4, 154], fill='#38bdf8')

    frames.append(img)

# Save as animated GIF
frames[0].save('workflow_pipeline.gif', save_all=True, append_images=frames[1:], duration=100, loop=0)
print("Saved workflow_pipeline.gif successfully!")
