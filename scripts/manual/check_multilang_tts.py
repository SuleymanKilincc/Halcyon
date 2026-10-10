"""
Test script for multi-language TTS functionality.
Tests Turkish and English language detection and voice switching.
"""

import pyttsx3
from langdetect import detect, LangDetectException

def test_langdetect():
    """Test language detection library."""
    print("="*60)
    print("TESTING LANGUAGE DETECTION")
    print("="*60)
    
    test_texts = [
        ("Hello, how are you today?", "en"),
        ("Merhaba, nasılsın bugün?", "tr"),
        ("I am creating a Python file.", "en"),
        ("Bir Python dosyası oluşturuyorum.", "tr"),
        ("File created successfully", "en"),
        ("Dosya başarıyla oluşturuldu", "tr"),
        ("The weather is nice today.", "en"),
        ("Bugün hava çok güzel.", "tr"),
    ]
    
    correct = 0
    for text, expected in test_texts:
        try:
            detected = detect(text)
            status = "✓" if detected == expected else "✗"
            print(f"{status} '{text[:40]}...' -> {detected} (expected: {expected})")
            if detected == expected:
                correct += 1
        except LangDetectException as e:
            print(f"✗ '{text[:40]}...' -> ERROR: {e}")
    
    print(f"\nAccuracy: {correct}/{len(test_texts)} ({100*correct//len(test_texts)}%)")
    print()

def list_available_voices():
    """List all available TTS voices."""
    print("="*60)
    print("AVAILABLE TTS VOICES")
    print("="*60)
    
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        
        turkish_voices = []
        english_voices = []
        other_voices = []
        
        for i, voice in enumerate(voices):
            voice_name = voice.name.lower()
            voice_id = voice.id.lower()
            
            # Turkish detection
            if any(keyword in voice_name or keyword in voice_id 
                   for keyword in ['turkish', 'turk', 'tr_tr', 'tolga', 'hazel']):
                turkish_voices.append(voice)
            # English detection
            elif any(keyword in voice_name or keyword in voice_id 
                     for keyword in ['english', 'en_us', 'en_gb', 'david', 'zira', 'mark']):
                english_voices.append(voice)
            else:
                other_voices.append(voice)
        
        print(f"\n🇹🇷 TURKISH VOICES: {len(turkish_voices)}")
        for voice in turkish_voices:
            print(f"  • {voice.name}")
            print(f"    ID: {voice.id}")
            print()
        
        print(f"\n🇬🇧 ENGLISH VOICES: {len(english_voices)}")
        for voice in english_voices:
            print(f"  • {voice.name}")
            print(f"    ID: {voice.id}")
            print()
        
        print(f"\n🌍 OTHER VOICES: {len(other_voices)}")
        for voice in other_voices[:5]:  # Show first 5 only
            print(f"  • {voice.name}")
        
        if len(other_voices) > 5:
            print(f"  ... and {len(other_voices) - 5} more")
        
        print()
        return engine, turkish_voices, english_voices
        
    except Exception as e:
        print(f"Error: {e}")
        return None, [], []

def test_voice_switching(engine, turkish_voices, english_voices):
    """Test voice switching between Turkish and English."""
    print("="*60)
    print("TESTING VOICE SWITCHING")
    print("="*60)
    
    if not engine:
        print("✗ TTS engine not available")
        return
    
    test_phrases = [
        ("Hello, this is a test in English.", "en", english_voices),
        ("Merhaba, bu Türkçe bir testtir.", "tr", turkish_voices),
    ]
    
    for text, lang, voices in test_phrases:
        if not voices:
            print(f"✗ No {lang.upper()} voice available for: '{text}'")
            continue
        
        print(f"\n🔊 Testing {lang.upper()}: '{text}'")
        print(f"   Using voice: {voices[0].name}")
        
        try:
            engine.setProperty('voice', voices[0].id)
            print(f"   Playing... (press Ctrl+C to skip)")
            engine.say(text)
            engine.runAndWait()
            print(f"   ✓ Done")
        except KeyboardInterrupt:
            engine.stop()
            print(f"   ⊘ Skipped")
        except Exception as e:
            print(f"   ✗ Error: {e}")
    
    print()

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("JARVIS MULTI-LANGUAGE TTS TEST")
    print("="*60)
    print()
    
    # Test 1: Language detection
    try:
        test_langdetect()
    except ImportError:
        print("✗ langdetect not installed. Run: pip install langdetect")
        print()
    
    # Test 2: List voices
    engine, turkish_voices, english_voices = list_available_voices()
    
    # Test 3: Voice switching
    if engine and (turkish_voices or english_voices):
        response = input("Test voice playback? (Y/N): ").strip().upper()
        if response in ['Y', 'YES']:
            test_voice_switching(engine, turkish_voices, english_voices)
    
    # Summary
    print("="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"✓ Language detection: {'Working' if 'langdetect' in dir() else 'Install langdetect'}")
    print(f"✓ TTS engine: {'Working' if engine else 'Not available'}")
    print(f"✓ Turkish voices: {len(turkish_voices)} found")
    print(f"✓ English voices: {len(english_voices)} found")
    print()
    
    if not turkish_voices:
        print("⚠️ WARNING: No Turkish voices found!")
        print("   On Windows, install Turkish language pack:")
        print("   Settings → Time & Language → Language → Add Turkish")
        print()
    
    if not english_voices:
        print("⚠️ WARNING: No English voices found!")
        print("   This is unusual. Check Windows TTS settings.")
        print()
    
    print("="*60)

if __name__ == "__main__":
    main()
