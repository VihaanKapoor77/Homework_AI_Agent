"""Send a live test through the running agent's normal Gradio chat API."""
import sys
from gradio_client import Client

client=Client('http://127.0.0.1:7860',verbose=False)
if '--run' not in sys.argv:
    client.view_api()
else:
    prompt=('Finish this timed DeltaMath round: solve all 10 questions within the '
            '100-second limit. Use the visible website controls and verify the final result. '
            'https://www.deltamath.com/app/student/5643551/35114314/eac45c7373614026750a77bb41f840ef')
    urls=[arg for arg in sys.argv[1:] if arg.startswith('https://www.deltamath.com/')]
    if urls:prompt='Solve exactly one question and verify website acceptance. '+urls[0]
    if urls and '--all' in sys.argv:
        prompt=('Complete all of it. Continue through every remaining question and unfinished skill in this assignment until the website confirms completion. '
                'For factoring expressions without an equals sign, leave the equation field empty and provide the factored expression in answers. '
                'When supplying an equation, transcribe the ORIGINAL displayed equation with both sides unchanged, without moving terms or simplifying it. '+urls[0])
    print('PROMPT: '+prompt,flush=True)
    job=client.submit(prompt,[], 'Math / DeltaMath',api_name='/chat')
    for output in job:
        print(repr(output),flush=True)
    print('FINAL: '+repr(job.result()),flush=True)
