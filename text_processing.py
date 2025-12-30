# text_processing.py
import re
import json
import traceback
import time
import openai
import logging
from app_state import VoicingMode
from transformers import AutoTokenizer # Import AutoTokenizer

class TextProcessor:
    def __init__(self, state, update_queue, logger: logging.Logger, selected_tts_engine_name: str):
        self.state = state
        self.update_queue = update_queue
        self.logger = logger
        self.selected_tts_engine_name = selected_tts_engine_name
        self.xtts_max_tokens = 400 # Max tokens for XTTS
        self.tokenizer = None

        if self.selected_tts_engine_name == "Coqui XTTS":
            try:
                self.tokenizer = AutoTokenizer.from_pretrained("coqui/XTTS-v2")
                self.logger.info("XTTS tokenizer initialized for text processing.")
            except Exception as e:
                self.logger.error(f"Failed to initialize XTTS tokenizer: {e}")
                self.tokenizer = None

    def expand_abbreviations(self, text_to_expand):
        abbreviations = {
            r"\bMr\.\s": "Mister ",
            r"\bMrs\.\s": "Missus ",
            r"\bMs\.\s": "Miss ",
            r"\bDr\.\s": "Doctor ",
            r"\bSt\.\s": "Saint ",
            r"\bCapt\.\s": "Captain ",
            r"\bCmdr\.\s": "Commander ",
            r"\bAdm\.\s": "Admiral ",
            r"\bGen\.\s": "General ",
            r"\bLt\.\s": "Lieutenant ",
            r"\bCol\.\s": "Colonel ",
            r"\bSgt\.\s": "Sergeant ",
            r"\bProf\.\s": "Professor ",
        }
        for abbr, expansion in abbreviations.items():
            text_to_expand = re.sub(abbr, expansion, text_to_expand, flags=re.IGNORECASE | re.UNICODE)
        return text_to_expand

    def determine_pov(self, text: str) -> str:
        text_lower = text.lower()
        first_person_count = len(re.findall(r'\b(i|me|my|mine|we|us|our|ours)\b', text_lower))
        second_person_count = len(re.findall(r'\b(you|your|yours)\b', text_lower))
        third_person_count = len(re.findall(r'\b(he|him|his|she|her|hers|it|its|they|them|their|theirs)\b', text_lower))
        if first_person_count > 0 and first_person_count >= second_person_count and first_person_count >= third_person_count:
            return "1st Person"
        elif second_person_count > 0 and second_person_count >= first_person_count and second_person_count >= third_person_count:
            return "2nd Person"
        elif third_person_count > 0 and third_person_count >= first_person_count and third_person_count >= second_person_count:
            return "3rd Person"
        elif first_person_count > 0: return "1st Person"
        elif second_person_count > 0: return "2nd Person"
        elif third_person_count > 0: return "3rd Person"
        return "Unknown"

    def run_rules_pass(self, text, voicing_mode):
        try:
            self.logger.info(f"Starting Pass 1 (rules-based analysis) with voicing mode: {voicing_mode.value}.")
            text = self.expand_abbreviations(text)
            results = []

            if voicing_mode == VoicingMode.NARRATOR:
                for line in text.splitlines():
                    if line.strip():
                        results.append({'speaker': 'Narrator', 'line': line.strip(), 'pov': self.determine_pov(line)})
                self.update_queue.put({'rules_pass_complete': True, 'results': results})
                return

            last_index = 0
            base_dialogue_patterns = {
                '"': r'"([^"]*)"',
                '‘': r'‘([^’]*)’',
                '“': r'“([^”]*)”'
            }

            if "'" in text:
                base_dialogue_patterns["'"] = r"'([^']*)'"  # Add single quote handling

            verbs_list_str = r"(said|replied|shouted|whispered|muttered|asked|protested|exclaimed|gasped|continued|began|explained|answered|inquired|stated|declared|announced|remarked|observed|commanded|ordered|suggested|wondered|thought|mused|cried|yelled|bellowed|stammered|sputtered|sighed|laughed|chuckled|giggled|snorted|hissed|growled|murmured|drawled|retorted|snapped|countered|concluded|affirmed|denied|agreed|acknowledged|admitted|queried|responded|questioned|urged|warned|advised|interjected|interrupted|corrected|repeated|echoed|insisted|pleaded|begged|demanded|challenged|taunted|scoffed|jeered|mocked|conceded|boasted|bragged|lectured|preached|reasoned|argued|debated|negotiated|proposed|guessed|surmised|theorized|speculated|posited|opined|ventured|volunteered|offered|added|finished|paused|resumed|narrated|commented|noted|recorded|wrote|indicated|signed|gestured|nodded|shrugged|pointed out)"
            speaker_name_bits = r"\w[\w\s\.]*"
            chapter_pattern = re.compile(r'^(Chapter\s+[\w\s\d\.:-]+|Book\s+[\w\s\d\.:-]+|Prologue|Epilogue|Part\s+[\w\s\d\.:-]+|Section\s+[\w\s\d\.:-]+)\s*[:.]?\s*([^\n]*)', re.IGNORECASE)
            
            speaker_tag_sub_pattern = f"(\s*,?\s*(?:({speaker_name_bits})\s+{verbs_list_str}|{verbs_list_str}\s+({speaker_name_bits}))\s*,?)"

            compiled_patterns = []
            for qc, dp in base_dialogue_patterns.items():
                full_pattern_regex = dp + f'{speaker_tag_sub_pattern}?'
                compiled_patterns.append({'qc': qc, 'pattern': re.compile(full_pattern_regex, re.IGNORECASE)})

            all_matches = []
            for item in compiled_patterns:
                for match in item['pattern'].finditer(text):
                    all_matches.append({'match': match, 'qc': item['qc']})

            all_matches.sort(key=lambda x: x['match'].start())
            sentence_end_pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'‘“])|(?<=[.!?])\n')

            for item in all_matches:
                match = item['match']
                quote_char = item['qc']
                start, end = match.span()

                narration_before = text[last_index:start].strip()
                if narration_before:
                    narration_lines = narration_before.split('\n')
                    for n_line in narration_lines:
                        stripped_n_line = n_line.strip()
                        if not stripped_n_line: continue

                        chapter_match = chapter_pattern.match(stripped_n_line)
                        if chapter_match:
                            line_data = {'speaker': 'Narrator', 'line': stripped_n_line, 'pov': self.determine_pov(stripped_n_line)}
                            line_data['is_chapter_start'] = True
                            line_data['chapter_title'] = stripped_n_line
                            results.append(line_data)
                            continue

                        sentences = sentence_end_pattern.split(stripped_n_line)
                        for sentence in sentences:
                            sentence = sentence.strip()
                            if sentence and len(sentence) > 2:  # Filter out lone periods/punctuation
                                pov = self.determine_pov(sentence)
                                line_data = {'speaker': 'Narrator', 'line': sentence, 'pov': pov}
                                results.append(line_data)

                dialogue_content = match.group(1).strip()
                full_dialogue_text = f"{quote_char}{dialogue_content}{quote_char}"
                
                if voicing_mode == VoicingMode.NARRATOR_AND_SPEAKER:
                    speaker_for_dialogue = "Speaker"
                else: # Cast mode
                    speaker_for_dialogue = "AMBIGUOUS"
                    if len(match.groups()) > 1 and match.group(2):
                        speaker_name_candidate = match.group(3) or match.group(4)
                        common_pronouns = {"he", "she", "they", "i", "we", "you", "it", "him", "her", "them", "his", "hers", "theirs", "my", "mine", "our", "ours", "your", "yours", "its"}
                        if speaker_name_candidate and speaker_name_candidate.strip().lower() not in common_pronouns:
                            speaker_for_dialogue = "Narrator" if speaker_name_candidate.strip().lower() == "narrator" else speaker_name_candidate.strip().title()

                dialogue_pov = self.determine_pov(dialogue_content)
                results.append({'speaker': speaker_for_dialogue, 'line': full_dialogue_text, 'pov': dialogue_pov})
                
                if len(match.groups()) > 1 and match.group(2):
                    raw_tag_text = match.group(2)
                    cleaned_tag_for_narration = raw_tag_text.lstrip(',').strip().replace('\n', ' ').replace('\r', '')
                    if cleaned_tag_for_narration:
                        pov = self.determine_pov(cleaned_tag_for_narration)
                        line_data = {'speaker': 'Narrator', 'line': cleaned_tag_for_narration, 'pov': pov}
                        results.append(line_data)

                last_index = end
            
            remaining_text_at_end = text[last_index:].strip()
            if remaining_text_at_end:
                narration_lines = remaining_text_at_end.split('\n')
                for n_line in narration_lines:
                    stripped_n_line = n_line.strip()
                    if not stripped_n_line: continue

                    chapter_match = chapter_pattern.match(stripped_n_line)
                    if chapter_match:
                        line_data = {'speaker': 'Narrator', 'line': stripped_n_line, 'pov': self.determine_pov(stripped_n_line)}
                        line_data['is_chapter_start'] = True
                        line_data['chapter_title'] = stripped_n_line
                        results.append(line_data)
                        continue

                    sentences = sentence_end_pattern.split(stripped_n_line)
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if sentence and len(sentence) > 2:  # Filter out lone periods/punctuation
                            pov = self.determine_pov(sentence)
                            line_data = {'speaker': 'Narrator', 'line': sentence, 'pov': pov}
                            results.append(line_data)

            self.logger.info("Pass 1 (rules-based analysis) complete.")
            self.update_queue.put({'rules_pass_complete': True, 'results': results})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Error during Pass 1 (rules-based analysis): {detailed_error}")
            self.update_queue.put({'error': f"Error during Pass 1 (rules-based analysis):\n\n{detailed_error}"})

    def _get_context_for_llm(self, original_index: int, context_size: int = 3) -> tuple[str, str]:
        """
        Gets a richer block of text before and after a given line index for LLM context.
        """
        # Get lines before the target line
        start_before = max(0, original_index - context_size)
        before_items = self.state.analysis_result[start_before:original_index]
        before_text = "\n".join([i['line'] for i in before_items]) if before_items else "[Start of Text]"

        # Get lines after the target line
        start_after = original_index + 1
        end_after = start_after + context_size
        after_items = self.state.analysis_result[start_after:end_after]
        after_text = "\n".join([i['line'] for i in after_items]) if after_items else "[End of Text]"
        
        return before_text, after_text

    def run_pass_2_llm_resolution(self, items_for_id, items_for_profiling):
        try:
            # Test connection first
            import requests
            test_url = "http://localhost:4247/v1/models"
            try:
                response = requests.get(test_url, timeout=5)
                if response.status_code != 200:
                    raise ConnectionError(f"LM Studio not responding (status {response.status_code})")
            except requests.exceptions.RequestException as e:
                raise ConnectionError(f"Cannot connect to LM Studio at localhost:4247 - {e}")
            
            # Increase timeout to accommodate larger local LLM processing times
            client = openai.OpenAI(base_url="http://localhost:4247/v1", api_key="not-needed", timeout=300.0)
            total_processed_count = 0
            
            system_prompt_id = "You are a data extraction tool. You follow instructions precisely. Your output is always a single line in the format: Speaker, Gender, AgeRange"

            user_prompt_template_id = """<text_excerpt>
<context_before>
{before_text}
</context_before>
<dialogue>
{dialogue_text}
</dialogue>
<context_after>
{after_text}
</context_after>
</text_excerpt>

<task>
Identify the speaker of the <dialogue> and their characteristics.
</task>

<output_format>
Speaker, Gender, AgeRange
</output_format>

<example>
Bob, Male, Adult
</example>

<response>
"""
            system_prompt_profile = "You are a data extraction tool. You follow instructions precisely. Your output is always a single line in the format: Speaker, Gender, AgeRange"

            user_prompt_template_profile = """<text_excerpt>
<known_speaker>
{known_speaker_name}
</known_speaker>
<context_before>
{before_text}
</context_before>
<dialogue>
{dialogue_text}
</dialogue>
<context_after>
{after_text}
</context_after>
</text_excerpt>

<task>
Determine the gender and age range for the <known_speaker>.
</task>

<output_format>
{known_speaker_name}, Gender, AgeRange
</output_format>

<example>
{known_speaker_name}, Male, Adult
</example>

<response>
"""

            for original_index, item in items_for_id:
                try:
                    before_text, after_text = self._get_context_for_llm(original_index)
                    dialogue_text = item['line']
                    user_prompt = user_prompt_template_id.format(before_text=before_text, dialogue_text=dialogue_text, after_text=after_text)
                    speaker_name, gender, age_range = self._call_llm_and_parse(client, system_prompt_id, user_prompt, original_index)
                    total_processed_count += 1
                    self.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': speaker_name, 'gender': gender, 'age_range': age_range})
                except openai.APITimeoutError:
                    self.logger.warning(f"Timeout processing item {original_index} with LLM."); total_processed_count += 1
                    self.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': 'TIMED_OUT', 'gender': 'Unknown', 'age_range': 'Unknown'})
                except Exception as e:
                     self.logger.error(f"Error processing item {original_index} with LLM: {e}"); total_processed_count += 1
                     self.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': 'UNKNOWN', 'gender': 'Unknown', 'age_range': 'Unknown'})

            for original_index, item in items_for_profiling:
                try:
                    known_speaker_name = item['speaker']
                    before_text, after_text = self._get_context_for_llm(original_index)
                    dialogue_text = item['line']
                    user_prompt = user_prompt_template_profile.format(known_speaker_name=known_speaker_name, before_text=before_text, dialogue_text=dialogue_text, after_text=after_text)
                    _, gender, age_range = self._call_llm_and_parse(client, system_prompt_profile, user_prompt, original_index)
                    total_processed_count += 1
                    self.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': known_speaker_name, 'gender': gender, 'age_range': age_range})
                except openai.APITimeoutError:
                    self.logger.warning(f"Timeout processing item {original_index} with LLM."); total_processed_count += 1
                    self.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': item['speaker'], 'gender': 'Unknown', 'age_range': 'Unknown'})
                except Exception as e:
                     self.logger.error(f"Error processing item {original_index} with LLM: {e}"); total_processed_count += 1
                     self.update_queue.put({'progress': total_processed_count - 1, 'original_index': original_index, 'new_speaker': item['speaker'], 'gender': 'Unknown', 'age_range': 'Unknown'})
            
            self.logger.info("Pass 2 (LLM resolution) completed.")
            self.update_queue.put({'pass_2_complete': True})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Critical error connecting to LLM or during LLM processing: {detailed_error}")
            self.update_queue.put({'error': f"A critical error occurred connecting to the LLM. Is your local server running?\n\nError: {e}"})


    def _call_llm_and_parse(self, client, system_prompt, user_prompt, original_index):
        prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant"
        # Wrap the LLM call with retries and exponential backoff to handle slow local models
        max_retries = 2
        attempt = 0
        while True:
            try:
                completion = client.chat.completions.create(
                    model="local-model",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    stop=["\n", "<|", ">|", "<|im_end|>"] # Stop on newline or the start of a special token
                )
                raw_response = completion.choices[0].message.content.strip()
                break
            except Exception as e:
                attempt += 1
                if attempt > max_retries:
                    self.logger.error(f"LLM call failed after {max_retries} retries for item {original_index}: {e}")
                    raise
                backoff = 2 * (2 ** (attempt - 1))
                self.logger.warning(f"LLM call timed out or errored for item {original_index}: {e}. Retrying in {backoff}s (attempt {attempt}/{max_retries})")
                time.sleep(backoff)
        
        # Clean up common model-generated junk before parsing
        junk_tokens = ["<|assistant|>", "<|user|>", "<|system|>", "<|endoftext|>", "</s>", "<answer>"]
        for token in junk_tokens:
            raw_response = raw_response.replace(token, "")
        raw_response = raw_response.strip()

        speaker_name, gender, age_range = "UNKNOWN", "Unknown", "Unknown"

        try:
            parts = [p.strip() for p in raw_response.split(',')]
            if len(parts) == 3:
                speaker_name = parts[0].title() if parts[0].lower() != "narrator" else "Narrator"
                gender = parts[1].title()
                age_range = parts[2].title()
                
                # Sanity check the parsed speaker name
                if not speaker_name or (' ' in speaker_name.strip() and len(speaker_name.strip()) > 30):
                    self.logger.warning(f"LLM response for item {original_index} resulted in a long/complex speaker name: '{speaker_name}'. Reverting to UNKNOWN.")
                    speaker_name = "UNKNOWN"
                quote_chars = "\'‘“’”"
                if len(speaker_name) > 1 and speaker_name.startswith(tuple(quote_chars)) and speaker_name.endswith(tuple(quote_chars)):
                    self.logger.warning(f"LLM returned a quote ('{speaker_name}') as the speaker for item {original_index}. Reverting to UNKNOWN.")
                    speaker_name = "UNKNOWN"
            else:
                speaker_name = raw_response.split('.')[0].split(',')[0].strip().title()
                if not speaker_name: speaker_name = "UNKNOWN"
                self.logger.warning(f"LLM response for item {original_index} not in expected format: '{raw_response}'.")
        except Exception as e_parse:
            self.logger.error(f"Error parsing LLM response for item {original_index}: '{raw_response}'. Error: {e_parse}")
        return speaker_name, gender, age_range

    def run_speaker_refinement_pass(self):
        try:
            # Test connection first
            import requests
            test_url = "http://localhost:4247/v1/models"
            try:
                response = requests.get(test_url, timeout=5)
                if response.status_code != 200:
                    raise ConnectionError(f"LM Studio not responding (status {response.status_code})")
            except requests.exceptions.RequestException as e:
                raise ConnectionError(f"Cannot connect to LM Studio at localhost:4247 - {e}")
            
            # Increase timeout to accommodate slower local LM processing
            client = openai.OpenAI(base_url="http://localhost:4247/v1", api_key="not-needed", timeout=300.0)
            
            # --- NEW LOGIC TO PREVENT CONTEXT OVERFLOW ---
            MAX_SPEAKERS_FOR_REFINEMENT = 150 # A reasonable limit to prevent overly long prompts
            
            # 1. Count lines for each speaker from the full analysis result
            speaker_counts = {}
            for item in self.state.analysis_result:
                speaker = item.get('speaker')
                if speaker and speaker.upper() not in {"AMBIGUOUS", "UNKNOWN", "TIMED_OUT"}:
                    speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1
            
            # 2. Sort speakers by count, descending
            sorted_speakers = sorted(speaker_counts.keys(), key=lambda s: speaker_counts[s], reverse=True)
            
            # 3. Truncate the list if it's too long
            speakers_to_refine = sorted_speakers
            if len(sorted_speakers) > MAX_SPEAKERS_FOR_REFINEMENT:
                speakers_to_refine = sorted_speakers[:MAX_SPEAKERS_FOR_REFINEMENT]
                self.logger.info(f"Cast list is very large ({len(sorted_speakers)} speakers). "
                                 f"Refining only the top {MAX_SPEAKERS_FOR_REFINEMENT} most frequent speakers to avoid context overflow.")

            speaker_context = []
            for speaker_name in speakers_to_refine:
                first_line = next((item['line'] for item in self.state.analysis_result if item['speaker'] == speaker_name), "No dialogue found.")
                speaker_context.append(f"- **{speaker_name}**: \"{first_line[:100]}...\"")
            context_str = "\n".join(speaker_context)

            # --- NEW STEP: Detect short/suspect quote fragments for Pass 2 and rejoin them ---
            # Goal: Fix cases where Pass 1 split contractions or short quoted fragments into separate lines.
            SHORT_SINGLE_QUOTE_MAX = 40
            SHORT_DOUBLE_QUOTE_MAX = 20

            candidates = []
            for idx, item in enumerate(self.state.analysis_result):
                line = item.get('line', '').strip()
                if not line or len(line) > SHORT_SINGLE_QUOTE_MAX:
                    continue
                # single quote candidate: short lines containing an apostrophe-like token or starting/ending with single quote
                if "'" in line:
                    # suspicious if it's short and either looks like a contraction or is mostly a quoted fragment
                    if re.match(r"^'?[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?'?$", line) or re.search(r"[A-Za-z0-9]+\'[A-Za-z0-9]+", line) or re.match(r"^'[^']+'$", line):
                        candidates.append({'idx': idx, 'type': 'single', 'line': line})
                        continue
                # double-quote short fragment candidate
                if line.startswith('"') and line.endswith('"') and len(line) <= SHORT_DOUBLE_QUOTE_MAX:
                    candidates.append({'idx': idx, 'type': 'double', 'line': line})

            if candidates:
                qc_system = "You are a helper that inspects short isolated lines that contain single or double quotes. For each candidate, decide whether the line is independent dialogue or a fragment (e.g., an apostrophe, short emphasis, or nickname) that should be appended to a neighboring line. Return a JSON array of objects: [{\"index\": <index>, \"is_dialogue\": true|false, \"suggested_action\": \"append_prev\"|\"append_next\"|\"keep\"}]. Provide short reasons."
                qc_user_template = "For each candidate, I provide the previous line (if any), the candidate line, and the next line (if any) as context. Context entries are prefixed PREV:, CAND:, NEXT:.\n\n{context}\n\nRespond with the described JSON array."

                # Build validation entries with context
                qc_entries = []
                for c in candidates:
                    idx = c['idx']
                    prev_line = self.state.analysis_result[idx - 1]['line'] if idx > 0 else ""
                    next_line = self.state.analysis_result[idx + 1]['line'] if idx < (len(self.state.analysis_result) - 1) else ""
                    qc_entries.append(f"PREV: {prev_line}\nCAND: {c['line']}\nNEXT: {next_line}")

                # Batch entries by char length similar to other validation steps
                qc_batches = []
                cur = []
                cur_len = 0
                for e in qc_entries:
                    l = len(e) + 1
                    if cur and (cur_len + l) > MAX_MODEL_CONTENT_CHARS:
                        qc_batches.append(cur)
                        cur = [e]
                        cur_len = len(e)
                    else:
                        cur.append(e)
                        cur_len += l
                if cur:
                    qc_batches.append(cur)

                # helper to parse the LLM response
                def _parse_quote_check_response(raw):
                    jmatch = re.search(r'```json\s*(\[.*?\])\s*```', raw, re.DOTALL)
                    if jmatch:
                        jstr = jmatch.group(1)
                    else:
                        s = raw.find('[')
                        e = raw.rfind(']')
                        if s != -1 and e != -1 and e > s:
                            jstr = raw[s:e+1]
                        else:
                            return None
                    try:
                        arr = json.loads(jstr)
                        return arr
                    except json.JSONDecodeError:
                        return None

                quote_actions = {}
                for bidx, batch in enumerate(qc_batches):
                    batch_context = "\n\n".join(batch)
                    user_text = qc_user_template.format(context=batch_context)
                    prompt = f"<|im_start|>system\n{qc_system}<|im_end|>\n<|im_start|>user\n{user_text}<|im_end|>\n<|im_start|>assistant"
                    try:
                        raw = _call_with_retries([{"role": "user", "content": prompt}])
                    except Exception as e:
                        self.logger.warning(f"Quote fragment validation failed for batch {bidx+1}: {e}. Proceeding with heuristic fallback.")
                        raw = ''

                    arr = _parse_quote_check_response(raw) if raw else None
                    if arr is None:
                        # Fallback heuristics: append single-quote contractions to previous, short double-quoted fragments to previous
                        for c in batch:
                            # extract index from the CAND line by matching in candidates list
                            m = re.search(r'CAND: (.*)', c)
                            if not m:
                                continue
                            cand_text = m.group(1).strip()
                            # find candidate index by matching line text (first match)
                            found = next((x for x in candidates if x['line'] == cand_text), None)
                            if not found:
                                continue
                            idx = found['idx']
                            if found['type'] == 'single':
                                quote_actions[idx] = 'append_prev'
                            else:
                                quote_actions[idx] = 'append_prev'
                        continue

                    for entry in arr:
                        try:
                            idx = int(entry.get('index'))
                            is_d = bool(entry.get('is_dialogue', True))
                            action = entry.get('suggested_action') or ('keep' if is_d else 'append_prev')
                            if not is_d:
                                quote_actions[idx] = action
                        except Exception:
                            continue

                # Apply actions: collect indexes to remove and apply merging
                if quote_actions:
                    self.logger.info(f"Applying quote fragment fixes for indexes: {quote_actions}")
                    new_results = []
                    skip_idxs = set(quote_actions.keys())
                    for i, item in enumerate(self.state.analysis_result):
                        if i in quote_actions:
                            act = quote_actions[i]
                            text = item.get('line', '')
                            if act == 'append_prev' and new_results:
                                prev = new_results[-1]
                                # join rules: if fragment starts with apostrophe, join without space
                                if text.startswith("'"):
                                    prev['line'] = (prev['line'].rstrip() + text)
                                else:
                                    prev['line'] = (prev['line'].rstrip() + ' ' + text)
                            elif act == 'append_next':
                                # we'll prepend to next line by applying when we reach it (store buffer)
                                # store in temp field
                                next_idx = i + 1
                                if next_idx < len(self.state.analysis_result):
                                    self.state.analysis_result[next_idx]['line'] = (text.rstrip() + ' ' + self.state.analysis_result[next_idx]['line'].lstrip())
                            # skip adding this item (it's merged)
                            continue
                        else:
                            new_results.append(item)
                    self.state.analysis_result = new_results
                    self.update_queue.put({'quote_fragment_fixapplied': True, 'fixed_indexes': list(quote_actions.keys())})

            # --- NEW STEP: Validate / normalize speaker names using the LLM ---
            try:
                val_system = "You are a helper that inspects short speaker-name candidates paired with a representative dialogue line. For each candidate, decide if it looks like a speaker name/title (is_name: true/false). If false and you can infer a likely proper name/title from the dialogue, provide suggested_name; otherwise suggested_name should be null. Provide a short reason for each decision."

                val_user_template = """Here are candidates and a representative line of dialogue for each (format: NAME | LINE).\n\n{context}\n\nReturn JSON array of objects: [{"original_name":"...","is_name":true|false,"suggested_name":null|"...","reason":"..."}]"""

                MAX_MODEL_CONTENT_CHARS = 2000
                MAX_SINGLE_LINE_CHARS = 200
                val_entries = []
                for speaker_name in speakers_to_refine:
                    first_line = next((item['line'] for item in self.state.analysis_result if item['speaker'] == speaker_name), "No dialogue found.")
                    line = first_line[:(MAX_SINGLE_LINE_CHARS-3)] + '...' if len(first_line) > (MAX_SINGLE_LINE_CHARS-3) else first_line
                    val_entries.append(f"{speaker_name} | {line}")

                # chunk into batches by characters
                val_batches = []
                cur = []
                cur_len = 0
                for e in val_entries:
                    l = len(e) + 1
                    if cur and (cur_len + l) > MAX_MODEL_CONTENT_CHARS:
                        val_batches.append(cur)
                        cur = [e]
                        cur_len = len(e)
                    else:
                        cur.append(e)
                        cur_len += l
                if cur:
                    val_batches.append(cur)

                name_corrections = {}

                def _parse_validation_response(raw):
                    # Try JSON first
                    jmatch = re.search(r'```json\s*(\[.*?\])\s*```', raw, re.DOTALL)
                    if jmatch:
                        jstr = jmatch.group(1)
                    else:
                        start = raw.find('[')
                        end = raw.rfind(']')
                        if start != -1 and end != -1 and end > start:
                            jstr = raw[start:end+1]
                        else:
                            # Heuristic fallback: try to extract lines like 'Name | line' with suggested_name: X
                            # Look for patterns like: Name: SuggestedName or Suggested: X
                            matches = re.findall(r'"?([A-Za-z0-9 _\-\.]+)"?\s*[:\-]\s*"?([A-Za-z0-9 _\-\.]+)"?', raw)
                            results = []
                            for m in matches:
                                results.append({'original_name': m[0].strip(), 'is_name': False, 'suggested_name': m[1].strip(), 'reason': 'heuristic parsed'})
                            if results:
                                return results
                            return None
                    try:
                        arr = json.loads(jstr)
                        return arr
                    except json.JSONDecodeError:
                        return None

                for bidx, batch in enumerate(val_batches):
                    batch_context = "\n".join(batch)
                    v_user = val_user_template.format(context=batch_context)
                    v_prompt = f"<|im_start|>system\n{val_system}<|im_end|>\n<|im_start|>user\n{v_user}<|im_end|>\n<|im_start|>assistant"
                    self.logger.info(f"Sending validation batch {bidx+1}/{len(val_batches)} to LLM (approx {len(batch_context)} chars)")
                    try:
                        raw = _call_with_retries([{"role": "user", "content": v_prompt}])
                    except Exception as e:
                        self.logger.warning(f"Name validation request failed for batch {bidx+1}: {e}. Attempting to split batch and retry.")
                        if len(batch) > 1:
                            mid = len(batch) // 2
                            # Replace current batch with two smaller ones to process
                            val_batches[bidx:bidx+1] = [batch[:mid], batch[mid:]]
                            continue
                        else:
                            self.logger.error(f"Single-line validation batch {bidx+1} failed and cannot be split further. Skipping.")
                            continue

                    arr = _parse_validation_response(raw)
                    if arr is None:
                        self.logger.warning(f"Name validation: no usable response for batch {bidx+1}. Raw: {raw[:200]}")
                        continue

                    for entry in arr:
                        orig = None
                        is_name = False
                        suggested = None
                        if isinstance(entry, dict):
                            orig = entry.get('original_name')
                            is_name = bool(entry.get('is_name'))
                            suggested = entry.get('suggested_name') if entry.get('suggested_name') else None
                        elif isinstance(entry, str):
                            # Try to parse a 'original_name: X, is_name: true, suggested_name: Y' style string
                            m = re.search(r'original_name\W*[:=]\W*"?([A-Za-z0-9 _\-\.]+)"?', entry, re.I)
                            if m:
                                orig = m.group(1).strip()
                            m2 = re.search(r'is_name\W*[:=]\W*(true|false)', entry, re.I)
                            if m2:
                                is_name = m2.group(1).lower() == 'true'
                            m3 = re.search(r'suggested_name\W*[:=]\W*"?([A-Za-z0-9 _\-\.]+)"?', entry, re.I)
                            if m3:
                                suggested = m3.group(1).strip()
                        if not orig:
                            continue
                        if is_name:
                            name_corrections[orig] = True
                        else:
                            name_corrections[orig] = suggested  # may be None

                # Build corrected speaker list as tuples (display_name, original_name)
                corrected_speakers = []

                def _infer_name_from_dialogue(line: str):
                    # Try to find patterns like: "Hello," John said. -> John
                    m = re.search(r'"[^"]+"\s*,?\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+(?:said|replied|asked|whispered|muttered|exclaimed|yelled|cried|laughed|responded|replied)', line)
                    if m:
                        return m.group(1)
                    # Pattern: "Hello, John," -> John
                    m = re.search(r'"[^"]*?,\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*[,]?"', line)
                    if m:
                        return m.group(1)
                    # Look for capitalized Name tokens in the line
                    m = re.search(r'\b([A-Z][a-z]{1,20}(?:\s[A-Z][a-z]{1,20})?)\b', line)
                    if m:
                        return m.group(1)
                    return None

                for speaker_name in speakers_to_refine:
                    corr = name_corrections.get(speaker_name, True)
                    # Find a representative line for inference
                    rep_line = next((item['line'] for item in self.state.analysis_result if item['speaker'] == speaker_name), "No dialogue found.")
                    if corr is True:
                        corrected_speakers.append((speaker_name, speaker_name))
                    elif corr is None:
                        # Attempt to infer a name from the dialogue
                        inferred = _infer_name_from_dialogue(rep_line)
                        if inferred:
                            corrected_speakers.append((inferred, speaker_name))
                        else:
                            corrected_speakers.append((speaker_name, speaker_name))
                    else:
                        # suggested string
                        corrected_speakers.append((corr, speaker_name))

                # Rebuild the speaker_context and context_str using corrected display names (preserve original mapping for line lookup)
                speaker_context = []
                for display_name, original_name in corrected_speakers:
                    first_line = next((item['line'] for item in self.state.analysis_result if item['speaker'] == original_name), "No dialogue found.")
                    speaker_context.append(f"- **{display_name}**: \"{first_line[:100]}...\"")
                context_str = "\n".join(speaker_context)
            except Exception as e:
                self.logger.info(f"Name validation step failed, proceeding with original speaker names: {e}")

            system_prompt = "You are an expert literary analyst. Be VERY conservative - only group names if you are absolutely certain they refer to the same character. When in doubt, keep names separate."
            user_prompt = f"""Here is a list of speaker names from a book, along with a representative line of dialogue for each:

{context_str}

INSTRUCTIONS:
1. ONLY group names if they are clearly the same character (e.g., "John" and "John Smith", "Dr. Watson" and "Watson")
2. DO NOT group names that could be different characters (e.g., "The Doctor" and "Dr. Smith" could be different doctors)
3. DO NOT group generic titles ("The Captain", "The Officer", "The Man") with proper names unless explicitly connected
4. Keep 'Narrator' separate from all characters
5. When grouping, use the most complete/formal name as primary_name

Be conservative - it's better to have too many separate characters than to incorrectly merge different people.

Provide JSON with 'character_groups' array. Each group has 'primary_name' and 'aliases' array.

Example:
```json
{{
  "character_groups": [
    {{
      "primary_name": "John Smith",
      "aliases": ["John", "Johnny"]
    }},
    {{
      "primary_name": "The Doctor",
      "aliases": []
    }}
  ]
}}
```"""

            # If the speaker list is large, send it in batches that fit within a safe character budget
            MAX_MODEL_CONTENT_CHARS = 2000  # soft limit for the {context_str} portion to avoid exceeding model input size and timeouts
            MAX_SINGLE_LINE_CHARS = 200  # truncate any single speaker line to this maximum length

            def _call_with_retries(messages, max_retries=2, initial_backoff=2):
                attempt = 0
                while True:
                    try:
                        completion = client.chat.completions.create(
                            model="local-model",
                            messages=messages,
                            temperature=0.0
                        )
                        return completion.choices[0].message.content.strip()
                    except Exception as err:
                        # Recognize openai timeout wrapper and httpx read timeout
                        attempt += 1
                        if attempt > max_retries:
                            self.logger.error(f"LLM request failed after {max_retries} retries: {err}")
                            raise
                        backoff = initial_backoff * (2 ** (attempt - 1))
                        self.logger.warning(f"LLM request timeout/error: {err}. Retrying in {backoff}s (attempt {attempt}/{max_retries})")
                        time.sleep(backoff)

            # Prepare per-speaker lines (truncate if necessary)
            per_speaker_lines = []
            for speaker_line in speaker_context:
                if len(speaker_line) > MAX_SINGLE_LINE_CHARS:
                    truncated = speaker_line[:MAX_SINGLE_LINE_CHARS - 3] + '...'
                    per_speaker_lines.append(truncated)
                else:
                    per_speaker_lines.append(speaker_line)

            # Chunk into batches by character length
            batches = []
            current_batch = []
            current_len = 0
            for line in per_speaker_lines:
                line_len = len(line) + 1  # +1 for newline when joined
                if current_batch and (current_len + line_len) > MAX_MODEL_CONTENT_CHARS:
                    batches.append(current_batch)
                    current_batch = [line]
                    current_len = len(line)
                else:
                    current_batch.append(line)
                    current_len += line_len
            if current_batch:
                batches.append(current_batch)

            aggregated_groups = []
            for idx, batch in enumerate(batches):
                batch_context = "\n".join(batch)
                # Inject the batch into the user prompt
                batch_user_prompt = user_prompt.replace(context_str, batch_context)

                self.logger.info(f"Sending speaker list batch {idx+1}/{len(batches)} to LLM (approx {len(batch_context)} chars)")
                prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{batch_user_prompt}<|im_end|>\n<|im_start|>assistant"
                try:
                    raw_response = _call_with_retries([{"role": "user", "content": prompt}])
                except Exception as e:
                    self.logger.warning(f"Batch {idx+1} failed with error: {e}. Attempting to split into smaller batches.")
                    # If this batch has more than one line, split and process smaller pieces
                    if len(batch) > 1:
                        mid = len(batch) // 2
                        smaller_batches = [batch[:mid], batch[mid:]]
                        # Insert smaller batches to process next (preserve order): we replace the current batch with the two halves
                        batches[idx:idx+1] = smaller_batches
                        continue
                    else:
                        self.logger.error(f"Single-line batch {idx+1} failed and cannot be split further. Skipping.")
                        continue

                self.logger.info(f"LLM refinement response (batch {idx+1}): {raw_response}")

                # Extract JSON (support markdown-wrapped or bare JSON) with robust fallback
                # First try fenced JSON object, then a JSON array, then fall back to object braces
                json_match_obj = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
                json_match_arr = re.search(r'```json\s*(\[.*?\])\s*```', raw_response, re.DOTALL)
                if json_match_obj:
                    json_string = json_match_obj.group(1)
                elif json_match_arr:
                    json_string = json_match_arr.group(1)
                else:
                    # try to locate a raw JSON array first
                    start_index = raw_response.find('[')
                    end_index = raw_response.rfind(']')
                    if start_index != -1 and end_index != -1 and end_index > start_index:
                        json_string = raw_response[start_index:end_index+1]
                    else:
                        # fall back to extracting a single JSON object if present
                        start_index = raw_response.find('{')
                        end_index = raw_response.rfind('}')
                        if start_index != -1 and end_index != -1 and end_index > start_index:
                            json_string = raw_response[start_index:end_index+1]
                        else:
                            # Try a heuristic to extract simple groupings like Primary: [aliases]
                            self.logger.error(f"No JSON found in LLM response for batch {idx+1}. Response: {raw_response}")
                            continue

                try:
                    response_data = json.loads(json_string)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to decode JSON from LLM response for batch {idx+1}. Error: {e}. Raw: {json_string}")
                    continue

                # Support either {'character_groups': [...]} or a bare array of group objects
                if isinstance(response_data, dict):
                    batch_groups = response_data.get("character_groups", [])
                elif isinstance(response_data, list):
                    batch_groups = response_data
                else:
                    batch_groups = []
                if batch_groups:
                    aggregated_groups.extend(batch_groups)
            # Merge aggregated groups by primary_name (case-insensitive), combining aliases
            merged = {}
            for grp in aggregated_groups:
                primary = grp.get('primary_name', '').strip()
                aliases = grp.get('aliases', []) or []
                key = primary.lower() if primary else None
                if not key:
                    continue
                if key not in merged:
                    merged[key] = {'primary_name': primary, 'aliases': set(aliases)}
                else:
                    merged[key]['aliases'].update(aliases)

            # Normalize to the expected structure
            character_groups = []
            for k, v in merged.items():
                aliases_list = sorted(x for x in v['aliases'] if x and x.strip().lower() != v['primary_name'].strip().lower())
                character_groups.append({'primary_name': v['primary_name'], 'aliases': aliases_list})

            if not character_groups:
                raise ValueError("LLM did not return any character_groups across all batches.")

            self.update_queue.put({'speaker_refinement_complete': True, 'groups': character_groups})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Error during speaker refinement pass: {detailed_error}")
            self.update_queue.put({'error': f"Error during speaker refinement:\n\n{detailed_error}"})