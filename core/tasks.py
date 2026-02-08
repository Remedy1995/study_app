
import os, requests, logging
from celery import shared_task
from django.conf import settings
from .models import AudioLecture
from fpdf import FPDF
from dotenv import load_dotenv
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

load_dotenv()
logger = logging.getLogger(__name__)

# Utility to send WebSocket messages
def notify_ws(group_name, event_type, data):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "send_event",
            "event": event_type,
            "data": data,
        }
    )

@shared_task(bind=True)
def transcribe_audio(self, lecture_id):
    try:
        lecture = AudioLecture.objects.get(id=lecture_id)
        group_name = f"lecture_{lecture_id}"

        lecture.status = "In progress"
        lecture.save()
        notify_ws(group_name, "status_update", {"status": "In progress"})

        with open(lecture.audio_file.path, "rb") as f:
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                files={"file": f},
                data={"model": "whisper-large-v3-turbo"},
            )
            response.raise_for_status()
            data = response.json()
            transcript = data.get("text")

            if not transcript:
                raise ValueError("No 'text' found in response")

            lecture.transcript = transcript
            lecture.status = "Successful"
            lecture.save()

            notify_ws(group_name, "status_update", {
                "status": "Successful",
                "transcript": transcript
            })

            logger.info(f"Transcription successful for lecture {lecture_id}")

    except AudioLecture.DoesNotExist:
        logger.error(f"Lecture with id {lecture_id} does not exist.")
    except Exception as e:
        logger.error(f"Error transcribing audio for lecture {lecture_id}: {str(e)}")
        if "lecture" in locals():
            lecture.status = "Failed"
            lecture.save()
            notify_ws(f"lecture_{lecture_id}", "status_update", {"status": "Failed"})
        raise self.retry(exc=e, countdown=10, max_retries=3)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def summarize_transcript(self, lecture_id):
    """
    Summarizes a lecture transcript using the Groq API.
    Automatically retries up to 3 times if network/API errors occur.
    """
    lecture = None
    try:
        # ✅ Safely get lecture
        lecture = AudioLecture.objects.filter(id=lecture_id).first()
        if not lecture:
            logger.warning(f"No lecture found for ID: {lecture_id}")
            return

        if not lecture.transcript:
            msg = "Sorry, there is no transcript for this lecture."
            logger.warning(msg)
            lecture.summary = msg
            lecture.save()
            return

        group_name = f"lecture_{lecture_id}"
        notify_ws(group_name, "status_update", {"status": "Summarizing"})

        # ✅ Make API call
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "user", "content": f"Summarize this: {lecture.transcript}"}
                ],
            },
            timeout=60
        )

        data = response.json()
        logger.info("======================================================================")
        logger.info(data)

        # ✅ Handle non-200 or invalid responses
        if response.status_code != 200 or "choices" not in data:
            error_message = data.get("error", {}).get("message", "Sorry, data not available")
            lecture.summary = error_message
            lecture.save()
            notify_ws(group_name, "status_update", {"status": "Failed", "summary": error_message})
            logger.error(f"Groq API Error: {error_message}")
            return

        # ✅ Extract summary text
        summary_text = data["choices"][0]["message"]["content"].strip()
        lecture.summary = summary_text
        lecture.save()

        notify_ws(group_name, "status_update", {"status": "Summary ready", "summary": summary_text})
        logger.info(f"Successfully summarized lecture ID {lecture_id}")

    except requests.exceptions.RequestException as e:
        # ✅ Retry on network issues (up to 3 times)
        msg = f"Network error occurred: {str(e)}. Retrying..."
        logger.error(msg)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        if lecture:
            lecture.summary = "Network error: please try again later."
            lecture.save()
        if 'group_name' in locals():
            notify_ws(group_name, "status_update", {"status": "Failed", "summary": msg})

    except Exception as e:
        msg = f"Unexpected error occurred: {str(e)}"
        logger.error(msg)
        if lecture:
            lecture.summary = msg
            lecture.save()
        if 'group_name' in locals():
            notify_ws(group_name, "status_update", {"status": "Failed", "summary": msg})
           


@shared_task(bind=True, max_retries=3)
def export_summary_to_pdf(self, lecture_id):
    try:
        lecture = AudioLecture.objects.get(id=lecture_id)
        group_name = f"lecture_{lecture_id}"

        notify_ws(group_name, "status_update", {"status": "Exporting PDF"})
        
        # Add progress tracking
        notify_ws(group_name, "status_update", {"status": "Creating PDF layout"})
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        notify_ws(group_name, "status_update", {"status": "Adding content to PDF"})
        
        # Split long content into chunks to avoid memory issues
        title = lecture.title[:100]  # Limit title length
        summary = lecture.summary or "No summary available"
        
        # Add title
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, title, ln=True, align='C')
        pdf.ln(10)
        
        # Add summary with better formatting
        pdf.set_font("Arial", size=12)
        summary_lines = summary.split('\n')
        for line in summary_lines:
            if line.strip():
                pdf.multi_cell(0, 8, line.strip())
        
        notify_ws(group_name, "status_update", {"status": "Saving PDF file"})
        
        # Ensure directory exists
        path = os.path.join(settings.MEDIA_ROOT, f"summaries/lecture_{lecture_id}_summary.pdf")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Save PDF with error handling
        try:
            pdf.output(path)
        except Exception as pdf_error:
            logger.error(f"PDF generation error: {pdf_error}")
            raise self.retry(exc=pdf_error, countdown=5)
        
        # Update lecture with PDF file
        lecture.pdf_file.name = f"summaries/lecture_{lecture_id}_summary.pdf"
        lecture.save()
        
        notify_ws(group_name, "status_update", {
            "status": "PDF ready", 
            "pdf": lecture.pdf_file.url,
            "message": "PDF generated successfully!"
        })
        
        logger.info(f"PDF generated successfully for lecture {lecture_id}")
        
    except AudioLecture.DoesNotExist:
        logger.error(f"Lecture with id {lecture_id} does not exist.")
        notify_ws(f"lecture_{lecture_id}", "status_update", {
            "status": "Error", 
            "message": "Lecture not found"
        })
        
    except Exception as e:
        logger.error(f"Error generating PDF for lecture {lecture_id}: {str(e)}")
        notify_ws(f"lecture_{lecture_id}", "status_update", {
            "status": "Error", 
            "message": f"PDF generation failed: {str(e)}"
        })
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=10)


@shared_task
def generate_flashcards(lecture_id):
    print('I have started generating')
    lecture = AudioLecture.objects.get(id=lecture_id)
    group_name = f"lecture_{lecture_id}"

    notify_ws(group_name, "status_update", {"status": "Generating flashcards"})

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "user", "content": f"Generate 10 flashcards from this summary:\n\n{lecture.transcript}"}
            ],
        },
    )

    data = response.json()
    print('the data',data)
    if "error" in data:
        notify_ws(group_name, "status_update", {"status": "Error", "message": data["error"]["message"]})
        return {"status": "error", "message": data["error"]["message"]}

    flashcards_text = data["choices"][0]["message"]["content"]
    lecture.flashcards = flashcards_text
    print(f'Flashcards for lecture {lecture_id}  {flashcards_text}')
    lecture.save()

    notify_ws(group_name, "status_update", {"status": "Flashcards ready", "flashcards": flashcards_text})

    return {"status": "success", "flashcards": flashcards_text}
