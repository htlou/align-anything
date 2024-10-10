# Copyright 2024 PKU-Alignment Team. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import argparse
from align_anything.evaluation.inference.base_inference import *
from align_anything.evaluation.dataloader.base_dataloader import BaseDataLoader
from align_anything.utils.tools import read_eval_cfgs, dict_to_namedtuple, update_dict, custom_cfgs_to_dict
from align_anything.evaluation.eval_logger import EvalLogger
from threading import Lock
import numpy as np
import hpsv2
import os

file_lock = Lock()
class HPSv2DataLoader(BaseDataLoader):
    def init_tokenizer(self):
        pass

    def get_task_names(self):
        if isinstance(self.data_cfgs.task, list):
            return self.data_cfgs.task
        else:
            task_names = [
            self.data_cfgs.task
            ]
            return task_names

    def load_dataset(self, gen_dir):
        processed_inputs = []
        with open(gen_dir, 'r', encoding='utf-8') as file:
            datas = json.load(file)
        for data in datas:
            processed_inputs.append({
                'id': data['id'],
                'prompt': data['prompt'],
                'image_path': data['image_path'],
            })
        return processed_inputs

class HPSv2Generator(BaseInferencer):
    def evaluator(self, outputs, file_path):
        tot_score = []
        num_sum = 0

        for output in tqdm(outputs, desc="Evaluating"):
            prompt = output['prompt']
            img_path = output['image_path']
            num_sum += 1
            if os.path.exists(img_path):
                score = float(hpsv2.score(img_path, prompt, hps_version="v2.0")[0])
            else:
                score = 0.0
            tot_score.append(score)
            save_detail(prompt, '', '', img_path, score, file_path)
        
        return tot_score, num_sum
        
def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    _, unparsed_args = parser.parse_known_args()
    keys = [k[2:] for k in unparsed_args[0::2]]
    values = list(unparsed_args[1::2])
    unparsed_args = dict(zip(keys, values))
    
    dict_configs, infer_configs = read_eval_cfgs('hpsv2', 'vLLM')
    
    try:
        assert dict_configs or infer_configs, "Config file does not exist or is incomplete."
    except AssertionError as e:
        print("Config file is not exist or incomplete.")
        exit()

    for k, v in unparsed_args.items():
        if v == '' or v is None:
            continue
        dict_configs = update_dict(dict_configs, custom_cfgs_to_dict(k, v))
        infer_configs = update_dict(infer_configs, custom_cfgs_to_dict(k, v))
    
    dict_configs, infer_configs = dict_to_namedtuple(dict_configs), dict_to_namedtuple(infer_configs)
    model_config = dict_configs.default.model_cfgs
    eval_configs = dict_configs.default.eval_cfgs
    logger = EvalLogger('Evaluation', log_dir=eval_configs.output_dir)
    dataloader = HPSv2DataLoader(dict_configs)
    assert not (dataloader.num_shot > 0 and dataloader.cot), "Few-shot and chain-of-thought cannot be used simultaneously for this benchmark."
    eval_module = HPSv2Generator(model_config.model_id, model_config.model_name_or_path, model_config.model_max_length, 42)
    raw_outputs = dataloader.load_dataset(eval_configs.generation_output)
    
    os.makedirs(logger.log_dir, exist_ok=True)
    uuid_path = f"{logger.log_dir}/{eval_configs.uuid}"
    os.makedirs(uuid_path, exist_ok=True)

    tot_score = []
    tot_num_sum = 0
    file_path = f"{uuid_path}/default.json"
    score, num_sum = eval_module.evaluator(raw_outputs, file_path)
    tot_score += score
    tot_num_sum += num_sum

    eval_results = {
            'model_id': [dict_configs.default.model_cfgs.model_id],
            'num_fewshot': [eval_configs.n_shot],
            'chain_of_thought': [eval_configs.cot],
            'num_sum': [num_sum],
            'avg_score': [np.mean(score)*100],
            }
    logger.print_table(title=f'HPSv2 Benchmark', data=eval_results)
    logger.log('info', '+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
    logger.log('info', f"model_id: {eval_results['model_id'][0]},")
    logger.log('info', f"num_fewshot: {eval_results['num_fewshot'][0]},")
    logger.log('info', f"chain_of_thought: {eval_results['chain_of_thought'][0]},")
    logger.log('info', f"num_sum: {eval_results['num_sum'][0]},")
    logger.log('info', f"score: {eval_results['avg_score'][0]} (±{np.std(score)}),")
    logger.log('info', '+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')

if __name__ == '__main__':
    main()