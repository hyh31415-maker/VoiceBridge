import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from voicebridge import storage

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.patch=patch.object(storage,'DATA',Path(self.temp.name));self.patch.start()
    def tearDown(self):self.patch.stop();self.temp.cleanup()
    def test_voice_names_persist_and_duplicate_is_rejected(self):
        library=storage.VoiceLibrary();item=library.add('测试声音','cloud-test')
        library.rename(item['id'],'新名称')
        self.assertEqual(library.load()[-1]['name'],'新名称')
        with self.assertRaises(ValueError):library.add('新名称','other')
    def test_history_survives_interruption_and_searches_content(self):
        h=storage.History();identity=h.start('en','Ethan');h.put(identity,'a','source',1.2,'测试研究');h.put(identity,'b','translation',2.3,'Research');h.flush();h.db.close()
        h=storage.History()
        self.assertEqual(len(h.list('研究')),1);self.assertEqual(h.list()[0][-1],'意外中断，已恢复文字')
        self.assertIn('Research',storage.export_srt(h.lines(identity)));h.db.close()

if __name__=='__main__':unittest.main()

