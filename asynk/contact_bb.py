##
## Created       : Fri Apr 06 19:08:32 IST 2012
## Last Modified : Fri May 04 18:16:45 IST 2012
##
## Copyright (C) 2012 Sriram Karra <karra.etc@gmail.com>
##
## Licensed under the GPL v3
##
## This file defines a wrapper class around a BBDB Contact entry, by extending
## the Contact abstract base Contact class. BBDB is, of course, the Insidious
## Big Brother Data Base
##

import copy, logging, re, uuid
from   contact    import Contact
from   utils      import chompq, unchompq
import demjson, pimdb_bb, folder_bb, utils

class BBContact(Contact):
    """This class extends the Contact abstract base class to wrap a BBDB
    Contact"""

    def __init__ (self, folder, con=None, rec=None):
        """rec is the native string vector representation of a BBDB contact
        entry on disk."""

        Contact.__init__(self, folder, con)

        self.atts.update({'bbdb_folder' : None,})

        ## Sometimes we might be creating a contact object from a Google
        ## contact object or other entry which might have the ID in its sync
        ## tags field. if that is present, we should use it to initialize the
        ## itemid field for the current object

        conf = self.get_config()
        if con:
            try:
                pname_re = conf.get_profile_name_re()
                label    = conf.make_sync_label(pname_re, self.get_dbid())
                tag, itemid = con.get_sync_tags(label)[0]              
                self.set_itemid(itemid)
            except Exception, e:
                logging.debug('Potential new BBContact: %s', con.get_name())

            if folder.get_name():
                self.set_bbdb_folder(folder.get_name())

        if rec:
            self.set_rec(rec)
            self.init_props_from_rec(rec)

        if not self.get_itemid():
            iid = ('%s' % uuid.uuid1())
            logging.debug('Assigning UUID %s for new contact: %s', iid, 
                          self.get_name())
            self.set_itemid(iid)

        self.in_init(False)

    ##
    ## First the inherited abstract methods from the base classes
    ##

    def save (self):
        raise NotImplementedError

    ##
    ## Overridden methods
    ##

    def get_name (self):
        ret = self._get_prop('name')
        if ret:
            return ret

        ret = ''
        fn = self.get_firstname()
        if fn:
            ret += (fn + ' ')

        ln = self.get_lastname()
        if ln:
            ret += ln

        return ret

    ##
    ## Now onto the non-abstract methods.
    ##

    def get_bbdb_folder (self):
        return self._get_att('bbdb_folder')

    def set_bbdb_folder (self, bbdb_folder):
        return self._set_att('bbdb_folder', bbdb_folder)

    def get_rec (self):
        return self._get_att('rec')

    def set_rec (self, rec):
        return self._set_att('rec', rec)

    def init_props_from_rec (self, rec):
        con_re = self.get_store().get_con_re()
        parse_res = re.search(con_re, rec)

        if not parse_res:
            logging.critical('Could not Parse BBDB contact entry: %s', rec)
            return

        d = parse_res.groupdict()
        self._snarf_names_from_parse_res(d)
        self._snarf_aka_from_parse_res(d)
        self._snarf_company_from_parse_res(d)
        self._snarf_emails_from_parse_res(d)
        self._snarf_postal_from_parse_res(d)
        self._snarf_phones_from_parse_res(d)
        self._snarf_notes_from_parse_res(d)

    def init_rec_from_props (self):
        if self.dirty():
            self.set_updated(pimdb_bb.BBPIMDB.get_bbdb_time())

        rec = '['
        rec += self._get_names_as_string()   + ' '
        rec += self._get_aka_as_string()     + ' '
        rec += self._get_company_as_string() + ' '
        rec += self._get_phones_as_string()  + ' '
        rec += self._get_postal_as_string()  + ' '
        rec += self._get_emails_as_string()  + ' '
        rec += self._get_notes_as_string()
        rec += ' nil]'

        self.dirty(False)
        return rec

    def _snarf_names_from_parse_res (self, pr):
        n = pr['firstname']
        if n and n != 'nil':
            self.set_firstname(chompq(n))

        n = pr['lastname']
        if n and n != 'nil':
            self.set_lastname(chompq(n))

        # FIXME: Just what the hell is an 'Affix'? Just use the first one and
        # ditch the rest.
        affix = pr['affix']
        if affix and affix != 'nil':
            self.set_suffix(chompq(affix[0]))

    def _snarf_aka_from_parse_res (self, pr):
        aka = pr['aka']
        if aka and aka != 'nil':
            str_re = self.get_store().get_str_re()
            aka    = re.findall(str_re, aka)
            nick   = aka[0]
            rest   = aka[1:]
            if nick:
                self.set_nickname(chompq(nick))

            if rest and len(rest) > 0:
                ## Note that 'rest' is an array, and it will not be possible
                ## to serialize it when sending to Google or saving to Outlook
                ## etc. So let's just encode it in json format - our goto
                ## solution for such problems.
                self.add_custom('aka', demjson.encode(rest))

    def _snarf_company_from_parse_res (self, pr):
        cs = pr['company']

        if cs and cs != 'nil':
            ## The first company goes into the Company field, the rest we will
            ## push into the custom field (as aa json encoded string)
            str_re = self.get_store().get_str_re()
            cs = re.findall(str_re, cs)
            self.set_company(chompq(cs[0]))
            rest = cs[1:]
            if rest and len(rest) > 0:
                self.add_custom('company', demjson.encode(rest))

    def _snarf_emails_from_parse_res (self, pr):
        ems = pr['emails']

        if ems:
            str_re = self.get_store().get_str_re()
            ems = re.findall(str_re, ems)
            ems = [chompq(x) for x in ems]

            domains = self.get_email_domains()

            for em in ems:
                if em == 'nil':
                    continue

                home, work, other = self._classify_email_addr(em, domains)

                ## Note that the following implementation means if the same
                ## domain is specified in more than one category, it ends up
                ## being copied to every category. In effect this means when
                ## this is synched to google contacts, say, the GC entry will
                ## have the same email address twice for the record

                if home:
                    self.add_email_home(em)
                elif work:
                    self.add_email_work(em)
                elif other:
                    self.add_email_other(em)
                else:
                    self.add_email_work(em)

    def _classify_email_addr (self, addr, domains):
        """Return a tuple of (home, work, other) booleans classifying if the
        specified address falls within one of the domains."""

        res = {'home' : False, 'work' : False, 'other' : False}

        for cat in res.keys():
            try:
                for domain in domains[cat]:
                    if re.search((domain + '$'), addr):
                        res[cat] = True
            except KeyError, e:
                logging.warning('Invalid email_domains specification.')

        return (res['home'], res['work'], res['other'])

    def _snarf_postal_from_parse_res (self, pr):
        adr_re = self.get_store().get_adr_re()
        str_re = self.get_store().get_str_re()
        addrs  = re.findall(adr_re, pr['addrs'])

        for addr in addrs:
            label, val = addr[:2]
            add = '[' + label + ' ' + val + ']'
            res = re.search(adr_re, add)

            if res:
                addict = {}
                fields = res.groupdict()

                streets = fields['streets']
                sts = re.findall(str_re, streets)
                sts = [chompq(x) for x in sts]

                if sts:
                    addict.update({'street' : '\n'.join(sts)})

                city = fields['city']
                if city:
                    addict.update({'city' : chompq(city)})

                state = fields['state']
                if state:
                    addict.update({'state' : chompq(state)})

                country = fields['country']
                if country:
                    addict.update({'country' : chompq(country)})

                pin = fields['zip']
                if pin:
                    addict.update({'zip' : chompq(pin)})

                self.add_postal(chompq(label), addict)
            else:
                logging.error('bb:snarf_postal(): Huh? No match for add %s.',
                              add)

    def _snarf_phones_from_parse_res (self, pr):
        ph_re = self.get_store().get_ph_re()
        phs   = re.findall(ph_re, pr['phones']) if pr['phones'] else None

        if phs:
            for ph in phs:
                res = re.search(ph_re, '[' + ph[0] + ']')

                if res:
                    resg = res.groupdict()

                    if resg['structured']:
                        phnum = '+1 ' + resg['structured']
                    else:
                        phnum = chompq(resg['unstructured'])

                    label = chompq(resg['phlabel'])
                    self._classify_and_add_phone(label, (label, phnum))
                else:
                    logging.debug('Could not parse phone: %s', ph[0])

    def _classify_and_add_phone (self, label, num):
        nmap = self.get_phones_map()

        if not nmap:
            logging.error('Mapping of phone labels is not in Config. ' +
                          'Adding phone %s as Home phone')
            self.add_phone_home(num)
            return

        if re.search(nmap['phone_home'], label):
            self.add_phone_home(num)
        elif re.search(nmap['phone_work'], label):
            self.add_phone_work(num)
        elif re.search(nmap['phone_mob'], label):
            self.add_phone_mob(num)
        elif re.search(nmap['fax_home'], label):
            self.add_fax_home(num)
        elif re.search(nmap['fax_work'], label):
            self.add_fax_work(num)
        elif re.search(nmap['fax_other'], label):
            self.add_fax_other(num)
        else:
            self.add_phone_other(num)

    def _snarf_notes_from_parse_res (self, pr):
        """Parse the BBDB Notes entry; this contains most of the good
        stuff... including sync tags and stuff."""

        noted = self.get_notes_map()
        if not noted:
            logging.error('Error in Config file. No notes_map field for bb')
            return

        stag_re = self.get_store().get_sync_tag_re()
        note_re = self.get_store().get_note_re()
        notes = re.findall(note_re, pr['notes'])
        custom = {}

        self.set_bbdb_folder(None)

        # logging.debug('bb:snfpr:stag_re: %s', stag_re)
        # keys = [note[0] for note in notes]
        # logging.debug('bb:snfpr:Keys: %s', keys)

        for note in notes:
            (key, val) = note[:2]

            key = key.rstrip()
            val = chompq(val)

            if key == noted['created']:
                self.set_created(val)
            elif key == noted['updated']:
                self.set_updated(val)
            elif key == noted['itemid']:
                self.set_itemid(val)
            elif key == noted['prefix']:
                self.set_prefix(val)
            elif key == noted['gender']:
                self.set_gender(val)
            elif key == noted['title']:
                self.set_title(val)
            elif key == noted['dept']:
                self.set_dept(val)
            elif key == noted['ims']:
                logging.info('IMs not supported in this version.')
            elif key == noted['notes']:
                self.add_notes(val)
            elif key == noted['birthday']:
                if self._is_valid_date(val):
                    self.set_birthday(val)
            elif key == noted['anniv']:
                if self._is_valid_date(val):
                    self.set_anniv(val)
            elif re.search(stag_re, key):
                self.update_sync_tags(key.rstrip(), val)
            elif re.search(noted['web_home_re'], key):
                self.add_web_home(val)
            elif re.search(noted['web_work_re'], key):
                self.add_web_work(val)
            elif re.search(noted['middle_name'], key):
                self.add_middlename(val)
            elif re.search(noted['folder'], key):
                self.set_bbdb_folder(val)
                custom.update({key : val})
            else:
                ## The rest of the stuff go into the 'Custom' field...
                custom.update({key : val})

        if len(custom.keys()) > 0:
            self.update_custom(custom)

    def _is_valid_date (self, date, label):
        res = re.search('\d\d\d\d-(\d\d)-(\d\d)', date)
        if not res:
            logging.error(('%s for %s should be yyyy-mm-dd ' +
                           'format. Actual value: %s'),
                           label, self.get_name(), date)
            return False
        elif int(res.group(1)) > 12:
            logging.error('Invalid month (%d) in %s for %s',
                          int(res.group(1)), label, self.get_name())
            return False
        else:
            ## We should really check the date for validity as well, oh, well,
            ## later. FIXME
            return True

    def _get_names_as_string (self):
        ret = ''
        n = self.get_firstname()
        l = self.get_lastname()

        if (not l) and (not n):
            n = self.get_name()
            if n:
                ret = '"%s" nil' % n
            else:
                ret = 'nil nil'
        else:
            if n:
                ret += unchompq(n) + ' '
            else:
                ret += 'nil '

            if l:
                ret += unchompq(l) + ' '
            else:
                ret += 'nil '

        a = self.get_suffix()
        if a:
            ret += ' ' + unchompq(a)
        else:
            ret += 'nil'

        return ret

    def _get_aka_as_string (self):
        nick = self.get_nickname()
        if not nick:
            return 'nil'
        nick = unchompq(nick)

        aka = copy.deepcopy(self.get_custom('aka'))
        if aka:
            ## Note that we have inserted AKAs an json encoded array of
            ## strings.
            aka = demjson.decode(aka)
            aka.insert(0, nick)
            return('(' + ' '.join(aka) + ')')
        else:
            return '(' + nick + ')'

    def _get_company_as_string (self):
        comp1 = self.get_company()
        if not comp1:
            return 'nil'

        comp = copy.deepcopy(self.get_custom('company'))
        if comp and len(comp) > 0:
            comp = demjson.decode(comp)
            comp.insert(0, unchompq(comp1))
            return ('(' + ' '.join(comp) + ')')
        else:
            return 'nil'

    def _get_emails_as_string (self):
        ems = [unchompq(e) for e in self.get_email_home()]
        ems.extend([unchompq(e) for e in self.get_email_work()])
        ems.extend([unchompq(e) for e in self.get_email_other()])

        ret = ' '.join(ems)

        if ret == '':
            return 'nil'
        else:
            return '(' + ret + ')'

    def _get_phones_as_string (self):
        ## Note that any BBDB phone number that was structured in the North
        ## Amerial format will be munged into an equivalent string notation
        ## for our convenience

        ph  = self.get_phone_home()
        ph.extend(self.get_phone_work())
        ph.extend(self.get_phone_mob())
        ph.extend(self.get_phone_other())

        phs = ['[%s %s]' % (unchompq(l), unchompq(n)) for l,n in ph]
        ret = ' '.join(phs)
        if ret == '':
            return 'nil'
        else:
            return '(' + ret + ')'

    def _get_postal_as_string (self):
        ret = ''
        for l, a in self.get_postal().iteritems():
            ret += '[' + unchompq(l) + ' '

            if 'street' in a and a['street']:
                strts = a['street'].split('\n')
                ret += '(' + ' '.join([unchompq(x) for x in strts]) + ')'
            else:
                ret += 'nil'

            ret += ' ' + (unchompq(a['city'])    if a['city']    else '""')
            ret += ' ' + (unchompq(a['state'])   if a['state']   else '""')
            ret += ' ' + (unchompq(a['zip'])     if a['zip']     else '""')
            ret += ' ' + (unchompq(a['country']) if a['country'] else '""')

            ret += ']'

        if ret == '':
            return 'nil'
        else:
            return '(' + ret + ')'

    def _get_notes_as_string (self):
        noted = self.get_notes_map()
        if not noted:
            logging.error('_ge(): Error in Config. No notes_map field for bb')
            return

        ret =  '(bbdb-id . %s) ' % unchompq(self.get_itemid())
        ret += '(%s . %s) ' % (noted['created'], unchompq(self.get_created()))
        ret += '(%s . %s) ' % (noted['updated'], unchompq(self.get_updated()))

        p = self.get_prefix()
        g = self.get_gender()
        t = self.get_title()
        d = self.get_dept()
        b = self.get_birthday()
        a = self.get_anniv()
        i = self.get_im()
        n = self.get_notes()
        m = self.get_middlename()

        if p:
            ret += '(%s . %s) ' % (noted['prefix'],  unchompq(p))
        if g:
            ret += '(%s . %s) ' % (noted['gender'],  unchompq(g))
        if t:
            ret += '(%s . %s) ' % (noted['title'],   unchompq(t))
        if d:
            ret += '(%s . %s) ' % (noted['dept'],    unchompq(d))
        if i:
            logging.info('IMs not supported in this version')
        if b:
            ret += '(%s . %s) ' % (noted['birthday'], unchompq(b))
        if a:
            ret += '(%s . %s) ' % (noted['anniv'], unchompq(a))
        if n and len(n) > 0:
            ret += '(%s . %s) ' % (noted['notes'], unchompq(n[0]))
        if m and m != '':
            ret += '(%s . %s) ' % (noted['middle_name'], unchompq(m))

        ret += self._get_sync_tags_as_str() + ' '

        for label, note in self.get_custom().iteritems():
            if label in ['company', 'aka']:
                continue

            ret += '(%s . %s) ' % (label, unchompq(note))

        return '(' + ret + ')'

    def _get_sync_tags_as_str (self):
        conf     = self.get_config()
        pname_re = conf.get_profile_name_re()
        label    = conf.make_sync_label(pname_re, self.get_dbid())

        ret = ''
        i = 0
        for key, val in self.get_sync_tags().iteritems():
            # Skip any sync tag with BBDB IDs as values.
            if re.search(label, key) or not val:
                continue

            if i > 0:
                ret += ' '
            i += 1

            ret += '(' + key + ' . ' + unchompq(val) + ')'

        return ret