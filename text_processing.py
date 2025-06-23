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
            
            all_matches.sort(key=lambda x: x['match'].start())
            sentence_end_pattern = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'‘“])|(?<=[.!?])$')

            for item in all_matches:
                match = item['match']
                quote_char = item['qc']
                start, end = match.span()

                narration_before = text[last_index:start].strip()
                if narration_before:
                    sentences = sentence_end_pattern.split(narration_before)
                    for sentence in sentences:
                        if sentence and sentence.strip():
                            pov = self.determine_pov(sentence.strip())
                            line_data = {'speaker': 'Narrator', 'line': sentence.strip(), 'pov': pov}
                            chapter_match = chapter_pattern.match(sentence.strip())
                            if chapter_match:
                                line_data['is_chapter_start'] = True
                                line_data['chapter_title'] = chapter_match.group(0).strip()
                            results.append(line_data)

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
                sentences = sentence_end_pattern.split(remaining_text_at_end)
                for sentence in sentences:
                    if sentence and sentence.strip():
                        pov = self.determine_pov(sentence.strip())
                        line_data = {'speaker': 'Narrator', 'line': sentence.strip(), 'pov': pov}
                        chapter_match = chapter_pattern.match(sentence.strip())
                        if chapter_match:
                            line_data['is_chapter_start'] = True
                            line_data['chapter_title'] = chapter_match.group(0).strip()
                        results.append(line_data)

            self.logger.info("Pass 1 (rules-based analysis) complete.")
            self.update_queue.put({'rules_pass_complete': True, 'results': results})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Error during Pass 1 (rules-based analysis): {detailed_error}")
            self.update_queue.put({'error': f"Error during Pass 1 (rules-based analysis):\n\n{detailed_error}"})

    def run_pass_2_llm_resolution(self, items_for_id, items_for_profiling):
        try:
            client = openai.OpenAI(base_url="http://localhost:4247/v1", api_key="not-needed", timeout=30.0)
            total_processed_count = 0
            
            system_prompt_id = "You are a literary analyst. Your task is to identify the speaker of a specific line of dialogue, their likely gender, and their general age range, given surrounding context. Respond concisely according to the specified format."
            user_prompt_template_id = "Based on the context below, who is the speaker of the DIALOGUE line?\n\nCONTEXT BEFORE: {before_text}\nDIALOGUE: {dialogue_text}\nCONTEXT AFTER: {after_text}\n\nCRITICAL INSTRUCTIONS:\n1. Identify the SPEAKER of the DIALOGUE.\n2. Determine the likely GENDER of the SPEAKER (Male, Female, Neutral, or Unknown).\n3. Determine the general AGE RANGE of the SPEAKER (Child, Teenager, Young Adult, Adult, Elderly, or Unknown).\n4. Respond with ONLY these three pieces of information, formatted exactly as: SpeakerName, Gender, AgeRange\n   Example: Hunter, Male, Adult\n5. Do NOT add any explanation, extra punctuation, or other words to your response."
            system_prompt_profile = "You are a literary analyst. Your task is to determine the likely gender and age range for a known speaker, based on their dialogue and surrounding context. Respond concisely according to the specified format."
            user_prompt_template_profile = "The speaker of the DIALOGUE line is known to be '{known_speaker_name}'.\nBased on the context below, what is their likely gender and age range?\n\nCONTEXT BEFORE: {before_text}\nDIALOGUE: {dialogue_text}\nCONTEXT AFTER: {after_text}\n\nCRITICAL INSTRUCTIONS:\n1. The SPEAKER is '{known_speaker_name}'.\n2. Determine the likely GENDER of the SPEAKER (Male, Female, Neutral, or Unknown).\n3. Determine the general AGE RANGE of the SPEAKER (Child, Teenager, Young Adult, Adult, Elderly, or Unknown).\n4. Respond with ONLY these three pieces of information, formatted exactly as: SpeakerName, Gender, AgeRange\n   Example: {known_speaker_name}, Male, Adult\n5. Do NOT add any explanation, extra punctuation, or other words to your response."

            for original_index, item in items_for_id:
                try:
                    before_text = self.state.analysis_result[original_index - 1]['line'] if original_index > 0 else "[Start of Text]"
                    dialogue_text = item['line']
                    after_text = self.state.analysis_result[original_index + 1]['line'] if original_index < len(self.state.analysis_result) - 1 else "[End of Text]"
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
                    before_text = self.state.analysis_result[original_index - 1]['line'] if original_index > 0 else "[Start of Text]"
                    dialogue_text = item['line']
                    after_text = self.state.analysis_result[original_index + 1]['line'] if original_index < len(self.state.analysis_result) - 1 else "[End of Text]"
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
            temperature=0.0
        )
        raw_response = completion.choices[0].message.content.strip()
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
            speaker_context = []
            for speaker_name in self.state.cast_list:
                if speaker_name.upper() in {"AMBIGUOUS", "UNKNOWN", "TIMED_OUT"}: continue
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