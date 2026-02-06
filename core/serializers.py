from rest_framework import serializers
from .models import AudioLecture,CustomUser
from rest_framework_simplejwt.tokens import RefreshToken
import os


class EmptySerializer(serializers.Serializer):
      pass

class AudioLectureSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudioLecture
        audio_file = serializers.FileField(required=True)
        fields = '__all__'
        read_only_fields = ['user', 'transcript', 'summary', 'pdf_file', 'created_at']

    def validate_audio_file(self, value):
        ext = os.path.splitext(value.name)[1].lower()
        allowed_extensions = ['.mp3', '.wav', '.m4a']
        if ext not in allowed_extensions:
            raise serializers.ValidationError(f"Unsupported file type: {ext}. Only MP3, WAV, or M4A files are allowed.")
        return value
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)



class RegisterSerializer(serializers.ModelSerializer):
    tokens = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password', 'tokens')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = CustomUser.objects.create_user(**validated_data)
        return user

    def get_tokens(self, obj):
        refresh = RefreshToken.for_user(obj)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }