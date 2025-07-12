# text_processing.py
import re
import json
import traceback
import openai
import logging

class TextProcessor:
    def __init__(self, state, update_queue, logger: logging.Logger):
        self.state = state
        self.update_queue = update_queue
        self.logger = logger

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

    def run_rules_pass(self, text):
        try:
            self.logger.info("Starting Pass 1 (rules-based analysis).")
            text = self.expand_abbreviations(text)
            results = []
            last_index = 0
            base_dialogue_patterns = {
                '"': r'"([^"]*)"',
                "'": r"'([^']*)'",
                '‘': r'‘([^’]*)’',
                '“': r'“([^”]*)”'
            }
            verbs_list_str = (r"(said|replied|shouted|whispered|muttered|asked|protested|exclaimed|gasped|continued|began|explained|answered|inquired|stated|declared|announced|remarked|observed|commanded|ordered|suggested|wondered|thought|mused|cried|yelled|bellowed|stammered|sputtered|sighed|laughed|chuckled|giggled|snorted|hissed|growled|murmured|drawled|retorted|snapped|countered|concluded|affirmed|denied|agreed|acknowledged|admitted|queried|responded|questioned|urged|warned|advised|interjected|interrupted|corrected|repeated|echoed|insisted|pleaded|begged|demanded|challenged|taunted|scoffed|jeered|mocked|conceded|boasted|bragged|lectured|preached|reasoned|argued|debated|negotiated|proposed|guessed|surmised|theorized|speculated|posited|opined|ventured|volunteered|offered|added|finished|paused|resumed|narrated|commented|noted|recorded|wrote|indicated|signed|gestured|nodded|shrugged|pointed out)")
            speaker_name_bits = r"\w[\w\s\.]*"
            chapter_pattern = re.compile(r"^(Chapter\s+\w+|Prologue|Epilogue|Part\s+\w+|Section\s+\w+)\s*[:.]?\s*([^\n]*)$", re.IGNORECASE)
            speaker_tag_sub_pattern = rf"""
                (
                    \s*,?\s*
                    (?:
                        (?:
                            ({speaker_name_bits})
                            \s+
                            (?:{verbs_list_str})
                        )
                        |
                        (?:
                            (?:{verbs_list_str})
                            \s+
                            ({speaker_name_bits})
                        )
                    )
                    (?:[\s\w\.,!?;:-]*)
                )
            """
            compiled_patterns = []
            for qc, dp in base_dialogue_patterns.items():
                full_pattern_regex = dp + f'{speaker_tag_sub_pattern}?'
                compiled_patterns.append({'qc': qc, 'pattern': re.compile(full_pattern_regex, re.IGNORECASE | re.VERBOSE)})

            all_matches = []
            for item in compiled_patterns:
                for match in item['pattern'].finditer(text):
                    all_matches.append({'match': match, 'qc': item['qc']})
            single_quote_pattern = r"(?<!\w)'(?=[^'\n]+[^'\w\s])([^']+)(?=[^'\n]+[^'\w\s])'(?!\w)"
            for match in re.finditer(single_quote_pattern, text):
                all_matches.append({'match': match, 'qc': "'"})


            all_matches.sort(key=lambda x: x['match'].start())
            sentence_end_pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'‘“])|(?<=[.!?])$')

            for item in all_matches:
                match = item['match']
                quote_char = item['qc']
                start, end = match.span()

                narration_before = text[last_index:start].strip()
                if narration_before:
                   # First, split by lines for potential chapter detection
                    narration_lines = narration_before.split('\n')
                    for n_line in narration_lines:
                        stripped_n_line = n_line.strip()
                        if not stripped_n_line: continue # Skip empty lines

                        # Check for chapter on the stripped line
                        chapter_match = chapter_pattern.match(stripped_n_line)
                        if chapter_match:
                            # If it's a chapter, add it as a narrator line with chapter info
                            line_data = {'speaker': 'Narrator', 'line': stripped_n_line, 'pov': self.determine_pov(stripped_n_line)}
                        if chapter_match:
                            line_data['is_chapter_start'] = True
                            line_data['chapter_title'] = stripped_n_line # Use the whole line as title
                            results.append(line_data)
                            self.logger.debug(f"Pass 1: Detected chapter: {stripped_n_line}")
                            continue # Don't process this line further as a regular sentence

                        # If not a chapter, then split into sentences for regular narration
                        sentences = sentence_end_pattern.split(stripped_n_line)
                        for sentence in sentences:
                            if sentence and sentence.strip():
                                pov = self.determine_pov(sentence.strip())
                                line_data = {'speaker': 'Narrator', 'line': sentence.strip(), 'pov': pov}
                                results.append(line_data)
                                self.logger.debug(f"Pass 1: Added Narrator (before): {results[-1]}")

                dialogue_content = match.group(1).strip()
                full_dialogue_text = f"{quote_char}{dialogue_content}{quote_char}"
                speaker_for_dialogue = "AMBIGUOUS"
                tag_text_for_narration = None

                if match.group(2):
                    raw_tag_text = match.group(2)
                    speaker_name_candidate = match.group(3) or match.group(4)
                    common_pronouns = {"he", "she", "they", "i", "we", "you", "it"}
                    if speaker_name_candidate and speaker_name_candidate.strip().lower() in common_pronouns:
                        speaker_name_candidate = None

                    if speaker_name_candidate and speaker_name_candidate.strip():
                        speaker_for_dialogue = "Narrator" if speaker_name_candidate.strip().lower() == "narrator" else speaker_name_candidate.strip().title()
                    
                    cleaned_tag_for_narration = raw_tag_text.lstrip(',').strip().replace('\n', ' ').replace('\r', '')
                    if cleaned_tag_for_narration:
                        tag_text_for_narration = cleaned_tag_for_narration
                
                dialogue_pov = self.determine_pov(dialogue_content)
                results.append({'speaker': speaker_for_dialogue, 'line': full_dialogue_text, 'pov': dialogue_pov})
                
                if tag_text_for_narration:
                    pov = self.determine_pov(tag_text_for_narration)
                    line_data = {'speaker': 'Narrator', 'line': tag_text_for_narration, 'pov': pov}
                    chapter_match = chapter_pattern.match(tag_text_for_narration)
                    if chapter_match:
                        line_data['is_chapter_start'] = True
                        line_data['chapter_title'] = chapter_match.group(0).strip()
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
                        self.logger.debug(f"Pass 1: Detected chapter: {stripped_n_line}")
                        continue

                    sentences = sentence_end_pattern.split(stripped_n_line)
                    for sentence in sentences:
                        if sentence and sentence.strip():
                            pov = self.determine_pov(sentence.strip())
                            line_data = {'speaker': 'Narrator', 'line': sentence.strip(), 'pov': pov}
                            results.append(line_data)
                            self.logger.debug(f"Pass 1: Added Narrator (after): {results[-1]}")

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
            client = openai.OpenAI(base_url="http://localhost:4247/v1", api_key="not-needed", timeout=60.0)
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
        completion = client.chat.completions.create(
            model="local-model",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.0,
            stop=["\n", "<|", ">|"], # Stop on newline or the start of a special token
            max_tokens=50 # Prevent run-on or junk responses
        )
        raw_response = completion.choices[0].message.content.strip()
        
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
                quote_chars = "\"\'‘“’”"
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
            client = openai.OpenAI(base_url="http://localhost:4247/v1", api_key="not-needed", timeout=60.0)
            
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

            system_prompt = "You are an expert literary analyst specializing in character co-reference resolution. Your task is to analyze a list of speaker names from a book and group them if they refer to the same character. You must also identify which names are temporary descriptions rather than proper names."
            user_prompt = f"""Here is a list of speaker names from a book, along with a representative line of dialogue for each:

{context_str}

CRITICAL INSTRUCTIONS:
1. Group names that refer to the same character. Use the most complete name as the primary name.
2. Identify names that are just descriptions (e.g., 'The Man', 'An Officer').
3. Do not group 'Narrator' with any character.
4. Provide your response as a valid JSON object with a single key 'character_groups'. The value should be an array of objects. Each object represents a final, unique character and contains two keys:
   - 'primary_name': The canonical name for the character (e.g., 'Captain Ian St. John').
   - 'aliases': An array of all other names from the input list that refer to this character (e.g., ['Hunter', 'The Captain', 'Ian St.John']).
5. If a name is a temporary description and cannot be linked to a specific character, create a group for it with the description as the 'primary_name' and an empty 'aliases' array.
6. If a name is unique and not an alias, it should be its own group with its name as 'primary_name' and an empty 'aliases' array.

Example JSON response format:
```json
{{
  "character_groups": [
    {{
      "primary_name": "Captain Ian St. John",
      "aliases": ["Hunter", "The Captain", "Ian St.John"]
    }},
    {{
      "primary_name": "Jimmy",
      "aliases": []
    }}
  ]
}}
```"""

            self.logger.info("Sending speaker list to LLM for refinement.")
            completion = client.chat.completions.create(
                model="local-model", 
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.0
            )
            raw_response = completion.choices[0].message.content.strip()
            self.logger.info(f"LLM refinement response: {raw_response}")

            # More robustly find JSON block, even if wrapped in markdown
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
            if json_match:
                json_string = json_match.group(1)
            else:
                # Fallback to finding the first and last brace
                start_index = raw_response.find('{')
                end_index = raw_response.rfind('}')
                if start_index != -1 and end_index != -1 and end_index > start_index:
                    json_string = raw_response[start_index:end_index+1]
                else:
                    raise ValueError("No JSON object or markdown JSON block found in the response.")
            
            try:
                response_data = json.loads(json_string)
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to decode JSON from LLM response. Raw string was: {json_string}. Error: {e}")
                raise ValueError(f"Could not parse a valid JSON object from the AI's response. See log for details.") from e

            character_groups = response_data.get("character_groups", [])
            if not character_groups: raise ValueError("LLM response did not contain 'character_groups'.")
            self.update_queue.put({'speaker_refinement_complete': True, 'groups': character_groups})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Error during speaker refinement pass: {detailed_error}")
            self.update_queue.put({'error': f"Error during speaker refinement:\n\n{detailed_error}"})