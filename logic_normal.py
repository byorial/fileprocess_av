# -*- coding: utf-8 -*-
#########################################################
# python
import os
import traceback
import time
import threading
import shutil
import re

# third-party

# sjva 공용
from framework import app, db, scheduler, path_app_root, celery
from framework.job import Job
from framework.util import Util
import framework.common.fileprocess as FileProcess

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, ModelItem
#########################################################


class LogicNormal(object):
    @staticmethod
    def scheduler_function():
        #LogicNormal.task()
        #return
        if app.config['config']['use_celery']:
            result = LogicNormal.task.apply_async()
            result.get()
        else:
            LogicNormal.task()

    @staticmethod
    @celery.task
    def task():
        try:
            logger.debug('%s INIT SCHEDULER', __name__)
            
            job_list = []
            if ModelSetting.get_bool('censored_use'):
                LogicNormal.process_censored()
            
            if ModelSetting.get_bool('uncensored_use'):
                LogicNormal.process_uncensored()

            if ModelSetting.get_bool('western_use'):
                LogicNormal.process_western()

            if ModelSetting.get_bool('normal_use'):
                LogicNormal.process_normal()
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False


    @staticmethod
    def get_path_list(key):
        tmps = ModelSetting.get_list(key)
        ret = []
        for t in tmps:
            if t.endswith('*'):
                dirname = os.path.dirname(t)
                listdirs = os.listdir(dirname)
                for l in listdirs:
                    ret.append(os.path.join(dirname, l))
            else:
                ret.append(t)
        return ret


    @staticmethod
    def process_censored():
        try:
            source = LogicNormal.get_path_list('censored_download_path')
            target = LogicNormal.get_path_list('censored_target_path')
            

            no_censored_path = ModelSetting.get('censored_temp_path')
            if len(source) == 0 or len(target) == 0 or no_censored_path == '':
                logger.info('Error censored. path info is empty')
                return
            # 쓰레기 정리
            for path in source:
                FileProcess.remove_small_file_and_move_target(path, ModelSetting.get_int('censored_min_size'))

            include_original_filename = ModelSetting.get_bool('include_original_filename')
            count = 0
            for path in source:
                filelist = os.listdir(path.strip())
                for filename in filelist:
                    file_path = os.path.join(path, filename)
                    if os.path.isdir(file_path):
                        continue
                    try:
                        entity = ModelItem('censored', path, filename)
                        
                        newfilename = FileProcess.change_filename_censored(filename)
                        logger.debug('newfilename : %s', newfilename)
                        
                        if newfilename is None: 
                            dest_filepath = os.path.join(no_censored_path, filename)
                            entity.move_type = 1
                            entity.target_dir = no_censored_path
                            entity.target_filename = filename
                        else:
                            # 이미 파일처리를 한거라면..
                            # newfilename 과 filename 이 [] 제외하고 같다면 처리한파일로 보자
                            # 그런 파일은 다시 원본파일명 옵션을 적용하지 않아야한다.
                            logger.debug(filename)
                            logger.debug(newfilename)
                            # adn-091-uncenrosed.mp4 
                            # 같이 시작하더라도 [] 가 없다면... 변경
                            # [] 없거나, 시작이 다르면..  완벽히 일치 하지 않으면
                            if filename != newfilename and ((filename.find('[') == -1 or filename.find(']') == -1) or not os.path.splitext(filename)[0].startswith(os.path.splitext(newfilename)[0])):
                                newfilename = FileProcess.change_filename_censored_by_save_original(include_original_filename, filename, newfilename)
                            else:
                                # 이미 한번 파일처리를 한것으로 가정하여 변경하지 않는다.
                                newfilename = filename
                                # 기존에 cd1 [..].mp4 는 []를 제거한다
                                match = re.search(r'cd\d(?P<remove>\s\[.*?\])', newfilename)
                                if match:
                                    newfilename = newfilename.replace(match.group('remove'), '')

                            logger.debug('%s => %s', filename, newfilename)
                            folder_name = newfilename.split('-')[0].upper()
                            censored_use_meta = ModelSetting.get('censored_use_meta')
                            target_folder = ''
                            use_meta_1_need = False
                            if censored_use_meta == '0' or censored_use_meta == '1':
                                for tmp in target:
                                    if os.path.exists(os.path.join(tmp.strip(), folder_name)):
                                        target_folder = os.path.join(tmp.strip(), folder_name)
                                        break
                                if target_folder == '':
                                    if censored_use_meta == '0':
                                        target_folder = os.path.join(target[0].strip(), folder_name)
                                    else:
                                        use_meta_1_need = True
                            
                            if use_meta_1_need or censored_use_meta == '2':
                                search_name = FileProcess.change_filename_censored(newfilename)
                                search_name = os.path.splitext(search_name)[0].replace('-', ' ')
                                search_name = re.sub('\s*\[.*?\]', '', search_name).strip()
                                match = re.search(r'(?P<cd>cd\d{1,2})$', search_name) 
                                if match:
                                    search_name = search_name.replace(match.group('cd'), '')

                                logger.debug(search_name)
                                data = FileProcess.search(search_name, do_trans=False)
                                #logger.debug(data)
                                
                                #if (len(data) == 1 and data[0]['score'] >= 95) or (len(data)>1 and data[0]['score']==100):
                                if data and ((len(data) == 1 and data[0]['score'] >= 95) or (len(data)>1 and data[0]['score']==100)):
                                #if score_100_last_index != -1:
                                    find_meta = True
                                    if data[0]['meta'] == 'dmm':
                                        target_folder = os.path.join(ModelSetting.get('censored_meta_dmm_path'), folder_name)
                                    elif data[0]['meta'] == 'javdb':
                                        target_folder = os.path.join(ModelSetting.get('censored_meta_javdb_path'), folder_name)
                                else:
                                    target_folder = os.path.join(ModelSetting.get('censored_meta_no_path'), folder_name)
                                    

                            if not os.path.exists(target_folder):
                                os.makedirs(target_folder)    
                            
                            dest_filepath = os.path.join(target_folder, newfilename)
                            logger.debug('MOVE : %s %s' % (filename, dest_filepath))
                            entity.move_type = 0
                            entity.target_dir = target_folder
                            entity.target_filename = newfilename
                        if os.path.exists(dest_filepath):
                            logger.debug('EXISTS : %s', dest_filepath)
                            os.remove(file_path)
                            entity.move_type = 2
                            
                        if os.path.exists(file_path):
                            shutil.move(os.path.join(path, filename), dest_filepath)
                        count += 1
                        
                    except Exception as e:
                        logger.debug('Exception:%s', e)
                        logger.debug(traceback.format_exc())
                    finally:
                        entity.save()
                        pass
                    
        except Exception as e:
            logger.debug('Exception:%s', e)
            logger.debug(traceback.format_exc())
    



    @staticmethod
    def process_uncensored():
        try:
            source = LogicNormal.get_path_list('uncensored_download_path')
            target = LogicNormal.get_path_list('uncensored_target_path')

            
            # 폴더목록 넣기
            target_child_list = []
            for t in target:
                listdirs = os.listdir(t)
                for tt in listdirs:
                    #2020-06-16
                    tmp  = os.path.join(t, tt)
                    if os.path.isdir(tmp):
                        target_child_list.append(tmp)

            no_type_path = ModelSetting.get('uncensored_temp_path')
            if len(source) == 0 or len(target) == 0 or no_type_path == '':
                logger.info('Error censored. path info is empty')
                return
            # 쓰레기 정리
            for path in source:
                FileProcess.remove_small_file_and_move_target(path, ModelSetting.get_int('uncensored_min_size'))

            count = 0
            for path in source:
                filelist = os.listdir(path.strip())
                for filename in filelist:
                    file_path = os.path.join(path, filename)
                    if os.path.isdir(file_path):
                        continue
                    try:
                        entity = ModelItem('uncensored', path, filename)
                        use_meta = ModelSetting.get('uncensored_use_meta')
                        tmp = None
                        target_folder = None
                        if os.path.splitext(filename)[1] in ['.mp4', '.avi', '.mkv', '.ts', '.wmv', '.m2ts', '.smi', ',srt', '.ass']:
                            tmp = FileProcess.uncensored_filename_analyze(filename)

                        if tmp is None or use_meta == '0': 
                            logger.debug('tmp:%s use_meta:%s' % (tmp, use_meta))
                            
                            #continue
                            for t in target_child_list:
                                dirname = os.path.basename(t)
                                #logger.debug(dirname)
                                if filename.find(dirname) != -1:
                                    target_folder = t
                                    dest_filepath = os.path.join(target_folder, filename)
                                    entity.move_type = 3
                                    entity.target_dir = target_folder
                                    entity.target_filename = filename
                                    break
                            if target_folder is None: 
                                logger.debug('NOT UNCENSORED!!!! : %s ' % filename)
                                dest_filepath = os.path.join(no_type_path, filename)
                                entity.move_type = 1
                                entity.target_dir = no_type_path
                                entity.target_filename = filename
                        else:
                            logger.debug(filename)
                            logger.debug(tmp)
                            folder_name = tmp[0]
                            
                            newfilename = filename

                            if use_meta == '1':
                                target_folder = os.path.join(ModelSetting.get('uncensored_meta_unmatch_path'), folder_name)
                                if tmp[1] is not None:
                                    data = FileProcess.search(filename, only_javdb=True)
                                    logger.debug(data)
                                    if data and ((len(data) == 1 and data[0]['score'] >= 95) or (len(data)>1 and data[0]['score']==100)):
                                    #if data and len(data) == 1 and data[0]['score'] >= 95 or len(data)>1 and data[0]['score']==100:
                                        target_folder = os.path.join(ModelSetting.get('uncensored_meta_match_path'), folder_name)

                            if not os.path.exists(target_folder):
                                os.makedirs(target_folder)    
                            
                            if tmp[0] == 'fc2':
                                code = tmp[1].split('-')[1]
                                match = re.search(r'[-_](?P<no>\d)$', os.path.splitext(filename)[0])
                                if match:
                                    newfilename = filename.replace('%s%s' % (code, match.group(0)), '%scd%s' % (code, match.group('no')))
                                    logger.debug('filename : %s', newfilename)
                                
                                match = re.search(r'[-_](?P<no>[A-Z])$', os.path.splitext(filename)[0])
                                if match:
                                    no = ord(match.group('no')) - ord('A') + 1
                                    newfilename = filename.replace('%s%s' % (code, match.group(0)), '%scd%s' % (code, no))
                                    logger.debug('filename : %s', newfilename)

                            dest_filepath = os.path.join(target_folder, newfilename)
                            logger.debug('MOVE : %s %s' % (filename, dest_filepath))
                            entity.move_type = 0
                            entity.target_dir = target_folder
                            entity.target_filename = newfilename
                        
                        if os.path.exists(dest_filepath):
                            logger.debug('EXISTS : %s', dest_filepath)
                            os.remove(file_path)
                            entity.move_type = 2
                            continue
                        logger.debug('MOVE : %s => %s', filename, dest_filepath)
                        shutil.move(os.path.join(path, filename), dest_filepath)
                        count += 1
                        
                        
                    except Exception as e:
                        logger.debug('Exception:%s', e)
                        logger.debug(traceback.format_exc())
                    finally:
                        entity.save()
                        pass
                    
        except Exception as e:
            logger.debug('Exception:%s', e)
            logger.debug(traceback.format_exc())
    


    

    @staticmethod
    def process_western():
        try:
            source = LogicNormal.get_path_list('western_download_path')
            target = LogicNormal.get_path_list('western_target_path')
            logger.debug('source1 : %s', ModelSetting.get('western_download_path'))
            logger.debug('source2 : %s', source)
            target_child_list = []
            for t in target:
                listdirs = os.listdir(t)
                for tt in listdirs:
                    #2020-06-16
                    tmp  = os.path.join(t, tt)
                    if os.path.isdir(tmp):
                        target_child_list.append(tmp)
                    #target_child_list.append(os.path.join(t, tt))

            no_type_path = ModelSetting.get('western_temp_path')
            if len(source) == 0 or len(target) == 0 or no_type_path == '':
                logger.info('Error western. path info is empty')
                return
            # 쓰레기 정리
            ext_list = ModelSetting.get_list('western_remove_ext')
            if ext_list:
                for path in source:
                    FileProcess.remove_match_ext(path, ext_list)

            use_meta = ModelSetting.get('western_use_meta')
            for path in source:
                filelist = os.listdir(path.strip())
                for filename in filelist:
                    target_folder = None
                    file_path = os.path.join(path, filename)
                    entity = ModelItem('western', path, filename)

                    try:
                        if use_meta == '1':
                            data = FileProcess.search(filename, only_javdb=True)
                            if data and ((len(data) == 1 and data[0]['score'] >= 95) or (len(data)>1 and data[0]['score']==100)):
                                target_folder = os.path.join(ModelSetting.get('western_meta_match_path'), data[0]['id_show'].split('.')[0])
                                #logger.debug()
                                entity.move_type = 0
                                entity.target_dir = target_folder
                                entity.target_filename = filename

                                if not os.path.exists(target_folder):
                                    os.makedirs(target_folder)

                        if target_folder is None:
                            for t in target_child_list:
                                dirname = os.path.basename(t)
                                if filename.find(dirname) != -1:
                                    target_folder = t
                                    entity.move_type = 3
                                    break
                            if target_folder is None: 
                                logger.debug('NOT WESTERN!!!! : %s ' % filename)
                                target_folder = no_type_path
                                entity.move_type = 1
                                
                        
                        #if target_folder is None:
                        entity.target_dir = target_folder
                        entity.target_filename = filename

                        dest_filepath = os.path.join(target_folder, filename)
                        if os.path.exists(dest_filepath):
                            logger.debug('EXISTS : %s', dest_filepath)
                            os.remove(file_path)
                            entity.move_type = 2
                            continue
                        logger.debug('MOVE : %s => %s', filename, dest_filepath)
                        shutil.move(os.path.join(path, filename), dest_filepath)

                    except Exception as e:
                        logger.debug('Exception:%s', e)
                        logger.debug(traceback.format_exc())
                    finally:
                        entity.save()
                        pass
                    
        except Exception as e:
            logger.debug('Exception:%s', e)
            logger.debug(traceback.format_exc())
    



    @staticmethod
    def process_normal():
        try:
            source = LogicNormal.get_path_list('normal_download_path')
            target = LogicNormal.get_path_list('normal_target_path')


            target_child_list = []
            for t in target:
                listdirs = os.listdir(t)
                for tt in listdirs:
                    #target_child_list.append(os.path.join(t, tt))
                    #2020-06-16
                    tmp  = os.path.join(t, tt)
                    if os.path.isdir(tmp):
                        target_child_list.append(tmp)

            no_type_path = ModelSetting.get('normal_temp_path')
            if len(source) == 0 or len(target) == 0 or no_type_path == '':
                logger.info('Error normal. path info is empty')
                return
            # 쓰레기 정리
            for path in source:
                FileProcess.remove_small_file_and_move_target(path, ModelSetting.get_int('normal_min_size'))
            
            for path in source:
                filelist = os.listdir(path.strip())
                for filename in filelist:
                    target_folder = None
                    file_path = os.path.join(path, filename)
                    entity = ModelItem('normal', path, filename)

                    try:
                        for t in target_child_list:
                            dirname = os.path.basename(t)
                            if filename.find(dirname) != -1:
                                target_folder = t
                                entity.move_type = 0
                                break
                        if target_folder is None: 
                            logger.debug('not match normal!!!! : %s ' % filename)
                            target_folder = no_type_path
                            entity.move_type = 1
                                
                        entity.target_dir = target_folder
                        entity.target_filename = filename

                        dest_filepath = os.path.join(target_folder, filename)
                        if os.path.exists(dest_filepath):
                            logger.debug('EXISTS : %s', dest_filepath)
                            os.remove(file_path)
                            entity.move_type = 2
                            continue
                        logger.debug('MOVE : %s => %s', filename, dest_filepath)
                        shutil.move(os.path.join(path, filename), dest_filepath)

                    except Exception as e:
                        logger.debug('Exception:%s', e)
                        logger.debug(traceback.format_exc())
                    finally:
                        entity.save()
                        pass
                    
        except Exception as e:
            logger.debug('Exception:%s', e)
            logger.debug(traceback.format_exc())


    

    
    

    

    @staticmethod
    def is_uncensored(filename):
        try:
            tmp = LogicNormal.get_plex_filename_uncensored(filename)
            if tmp is not None:
                return True
            
            regex = [r'^(xxx-)?av-\d{5}(.*?){0,3}\.(.*?){3}$', r'^n\-?\d{4}', r'^t\-?\d{5}', r'^T\-?\d{5}']
            for r in regex:
                match = re.compile(r).search(filename)
                if match:
                    return True
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
        return False
        