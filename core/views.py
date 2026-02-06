from rest_framework import viewsets,status,generics
from rest_framework.decorators import action,api_view, permission_classes
from rest_framework.response import Response
from .models import AudioLecture,CustomUser
from rest_framework.permissions import IsAuthenticated
from .serializers import AudioLectureSerializer,RegisterSerializer,EmptySerializer
from .tasks import transcribe_audio, summarize_transcript, export_summary_to_pdf, generate_flashcards
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser


class AudioLectureViewSet(viewsets.ModelViewSet):
    queryset = AudioLecture.objects.all()
    serializer_class = AudioLectureSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]  # ✅ This enables file upload in Swagger

    @action(detail=True, methods=['post'],serializer_class=EmptySerializer)
    def transcribe(self, request, pk=None):
        try:
            lecture = self.get_object()
            print('my object is',lecture)
            if lecture.status == 'In progress':
                return Response({'status': 'Transcription already in progress'}, status=status.HTTP_202_ACCEPTED)
            
            transcribe_audio.delay(lecture.id)
            return Response({'status': 'Transcription started'}, status=status.HTTP_202_ACCEPTED)
        
        except AudioLecture.DoesNotExist:
            logger.error(f"Lecture with id {pk} does not exist.")
            return Response({'error': 'Lecture not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def summarize(self, request, pk=None):
        summarize_transcript.delay(pk)
        return Response({'status': 'summary generation started'})

    @action(detail=True, methods=['post'])
    def export_pdf(self, request, pk=None):
        export_summary_to_pdf.delay(pk)
        return Response({'status': 'pdf export started'})

    @action(detail=True, methods=['post'],serializer_class=EmptySerializer)
    def generate_flashcards(self, request, pk=None):
        task = generate_flashcards.delay(pk)
        return Response({'status': 'flashcard generation started', 'task_id': task.id})

class RegisterUserView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "message": "User registered successfully.",
                "user": {
                    "username": user.username,
                    "email": user.email
                },
                "tokens": serializer.data['tokens']
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)